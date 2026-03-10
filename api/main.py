from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import FileResponse
import redis
import uuid
import os
import logging
from kubernetes import client, config
import boto3

app = FastAPI(title="AI Media Factory API")

# Redis 연결
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

@app.get("/", response_class=FileResponse)
async def serve_frontend():
    """웹 UI 프론트엔드 서빙"""
    return FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))

import json

def _get_name_tag(tags):
    for tag in (tags or []):
        if tag['Key'] == 'Name':
            return tag['Value']
    return None


def _scan_single_account(ec2_client, account_id: str) -> dict:
    """boto3 ec2 클라이언트를 받아 해당 계정의 낭비 자원을 스캔합니다."""
    report = {
        "account_id": account_id,
        "unattached_ebs_volumes": [],
        "unassociated_eips": [],
        "error": None
    }
    try:
        volumes = ec2_client.describe_volumes(Filters=[{'Name': 'status', 'Values': ['available']}])
        for vol in volumes.get('Volumes', []):
            report["unattached_ebs_volumes"].append({
                "name": _get_name_tag(vol.get('Tags')),
                "id": vol['VolumeId'],
                "size_gb": vol['Size'],
                "type": vol['VolumeType']
            })

        addresses = ec2_client.describe_addresses()
        for addr in addresses.get('Addresses', []):
            if 'AssociationId' not in addr:
                report["unassociated_eips"].append({
                    "name": _get_name_tag(addr.get('Tags')),
                    "ip": addr['PublicIp'],
                    "allocation_id": addr['AllocationId']
                })
    except Exception as e:
        logging.error(f"계정 {account_id} 스캔 중 오류: {e}")
        report["error"] = str(e)
    return report


AWS_ACCOUNTS_CONFIG_PATH = os.getenv("AWS_ACCOUNTS_CONFIG_PATH", "/etc/aws-config/aws_accounts.json")

@app.get("/aws-waste")
def get_aws_waste():
    """AWS 계정(들)의 낭비 자원을 수집합니다.

    - 설정 파일 없음: 현재 자격증명 계정 단일 스캔
    - 설정 파일 있음: 파일의 계정 목록을 STS AssumeRole로 순회하며 멀티 스캔
    """
    # 설정 파일 로드 시도
    config = None
    if os.path.exists(AWS_ACCOUNTS_CONFIG_PATH):
        with open(AWS_ACCOUNTS_CONFIG_PATH, "r") as f:
            config = json.load(f)

    # 단일 계정 모드
    if not config or not config.get("accounts"):
        ec2 = boto3.client('ec2')
        result = _scan_single_account(ec2, account_id="current")
        result["name"] = "현재 계정"
        return {"accounts": {"current": result}}

    # 멀티 계정 모드
    role_name = config.get("role_name", "WasteScannerRole")
    accounts = config["accounts"]
    sts = boto3.client('sts')
    results = {}

    for account in accounts:
        account_id = account["id"]
        account_name = account.get("name", account_id)
        try:
            assumed = sts.assume_role(
                RoleArn=f"arn:aws:iam::{account_id}:role/{role_name}",
                RoleSessionName="WasteScannerSession"
            )
            creds = assumed['Credentials']
            ec2 = boto3.client(
                'ec2',
                aws_access_key_id=creds['AccessKeyId'],
                aws_secret_access_key=creds['SecretAccessKey'],
                aws_session_token=creds['SessionToken']
            )
            result = _scan_single_account(ec2, account_id)
            result["name"] = account_name
            results[account_id] = result
        except Exception as e:
            logging.error(f"계정 {account_name}({account_id}) AssumeRole 실패: {e}")
            results[account_id] = {"account_id": account_id, "name": account_name, "error": str(e)}

    return {"accounts": results}

@app.get("/k8s-waste")
def get_k8s_waste():
    """k8s 클러스터 내부의 낭비되는 자원(좀비 Pod, 고아 PVC 등)을 수집합니다."""
    waste_report = {
        "zombie_pods": [],
        "unbound_pvcs": [],
        "empty_deployments": [],
        "mock_data": False
    }
    
    try:
        # 클러스터 내부(Pod 안)에서 실행될 때 권한 획득
        try:
            config.load_incluster_config()
        except config.config_exception.ConfigException:
            # 로컬(맥북)에서 직접 파이썬 스크립트 띄울 때 테스트용
            config.load_kube_config()
            
        v1 = client.CoreV1Api()
        apps_v1 = client.AppsV1Api()
        
        # 1. 낭비되는 Pod (CrashLoopBackOff, Error, Evicted 등)
        pods = v1.list_pod_for_all_namespaces().items
        for pod in pods:
            if pod.status.phase in ["Failed", "Unknown"]:
                waste_report["zombie_pods"].append({"name": pod.metadata.name, "namespace": pod.metadata.namespace, "status": pod.status.phase})
            elif pod.status.container_statuses:
                for cs in pod.status.container_statuses:
                    if cs.state.waiting and cs.state.waiting.reason in ["CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull"]:
                        waste_report["zombie_pods"].append({"name": pod.metadata.name, "namespace": pod.metadata.namespace, "status": cs.state.waiting.reason})
        
        # 2. 연결되지 않은 고아 PVC (Pending/Lost)
        pvcs = v1.list_persistent_volume_claim_for_all_namespaces().items
        for pvc in pvcs:
            if pvc.status.phase != "Bound":
                capacity = pvc.status.capacity.get('storage', 'Unknown') if pvc.status.capacity else 'Unknown'
                waste_report["unbound_pvcs"].append({"name": pvc.metadata.name, "namespace": pvc.metadata.namespace, "status": pvc.status.phase, "capacity": capacity})
        
        # 3. 레플리카가 0인 Deployment (방치된 껍데기)
        deployments = apps_v1.list_deployment_for_all_namespaces().items
        for dep in deployments:
            if dep.spec.replicas == 0:
                waste_report["empty_deployments"].append({"name": dep.metadata.name, "namespace": dep.metadata.namespace})
                
    except Exception as e:
        # k8s 연결 실패 시 모의(Mock) 데이터 반환
        logging.error(f"K8s API 연결 실패, 모의 데이터 반환: {e}")
        waste_report["mock_data"] = True
        waste_report["zombie_pods"] = [
            {"name": "frontend-dev-pod-a1b2", "namespace": "dev-namespace", "status": "CrashLoopBackOff"},
            {"name": "batch-job-old-version", "namespace": "default", "status": "Evicted"}
        ]
        waste_report["unbound_pvcs"] = [
            {"name": "db-backup-pvc-2023", "namespace": "ai-media", "status": "Pending", "capacity": "50Gi"}
        ]
        
    return waste_report

@app.post("/generate-image")
async def generate_image(prompt: str, chat_id: str = None):
    """사용자로부터 텍스트 프롬프트를 받아 이미지 생성 작업을 큐에 넣습니다."""
    task_id = str(uuid.uuid4())
    
    # 큐에 작업 넣기 (List 사용: 'image_queue', JSON 형식 적용)
    task_payload = json.dumps({
        "task_id": task_id,
        "prompt": prompt,
        "chat_id": chat_id
    })
    r.lpush("image_queue", task_payload)
    
    return {
        "status": "접수 완료", 
        "task_id": task_id, 
        "chat_id": chat_id,
        "message": "이미지 생성 작업이 대기열에 추가되었습니다."
    }

@app.get("/health")
def health_check():
    return {"status": "ok"}
