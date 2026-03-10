from fastapi import FastAPI
import os
import logging
import boto3
import json

app = FastAPI(title="AWS Resource Scanner API")


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
    config = None
    if os.path.exists(AWS_ACCOUNTS_CONFIG_PATH):
        with open(AWS_ACCOUNTS_CONFIG_PATH, "r") as f:
            config = json.load(f)

    if not config or not config.get("accounts"):
        ec2 = boto3.client('ec2')
        result = _scan_single_account(ec2, account_id="current")
        result["name"] = "현재 계정"
        return {"accounts": {"current": result}}

    role_name = config.get("role_name", "aws-waste-scanner")
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


@app.get("/health")
def health_check():
    return {"status": "ok"}
