# AWS Resource Scanner

멀티 AWS 계정의 방치된 자원(EBS 볼륨, EIP)을 매일 자동 스캔하여 Gemini AI로 요약 후 Telegram으로 브리핑하는 봇입니다.

## 아키텍처

```
[n8n 스케줄 - 매일 10시]
        ↓
[FastAPI /aws-waste]  →  STS AssumeRole  →  각 계정 EC2 스캔
        ↓
[Gemini 2.5-flash AI 요약]
        ↓
[Telegram 브리핑 발송]
```

## 스캔 대상
- **미연결 EBS 볼륨**: status=available 상태인 볼륨 (Name 태그, 용량, 타입 포함)
- **미연결 EIP**: AssociationId 없는 탄력적 IP (Name 태그, IP, Allocation ID 포함)

## 시스템 요구사항
- Docker
- Kubernetes 클러스터 (Kind)
- `kubectl` 커맨드라인 툴

## 배포 가이드

### 1단계: AWS IAM 설정

**스캐너 계정** (`aws-waste-scanner` 사용자/역할)에 필요한 권한:
- `sts:AssumeRole` — 대상 계정 역할 Assume용
- `AmazonEC2ReadOnlyAccess` — 자체 계정 스캔용 (역할에도 동일하게 부여)

**각 대상 계정**의 `aws-waste-scanner` IAM 역할에 Trust Policy 추가:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"AWS": "arn:aws:iam::<스캐너_계정ID>:root"},
    "Action": "sts:AssumeRole"
  }]
}
```

대상 계정 역할에도 `AmazonEC2ReadOnlyAccess` 권한 부여 필요.

### 2단계: AWS 계정 설정 파일 생성

`config/aws_accounts.json` 생성 (이 파일은 커밋하지 마세요):
```json
{
  "role_name": "aws-waste-scanner",
  "accounts": [
    {"id": "123456789012", "name": "계정명1"},
    {"id": "987654321098", "name": "계정명2"}
  ]
}
```

K8s ConfigMap으로 등록:
```bash
kubectl create configmap aws-accounts-config \
  --from-file=aws_accounts.json=config/aws_accounts.json \
  -n ai-media
```

### 3단계: K8s 시크릿 생성

```bash
kubectl create secret generic aws-credentials-cp5 \
  --from-literal=AWS_ACCESS_KEY_ID=<키> \
  --from-literal=AWS_SECRET_ACCESS_KEY=<시크릿> \
  --from-literal=AWS_DEFAULT_REGION=ap-northeast-2 \
  -n ai-media
```

### 4단계: 도커 이미지 빌드 및 K8s 로드

```bash
docker build -t aws-resource-scanner-api:latest ./api
kind load docker-image aws-resource-scanner-api:latest --name <클러스터명>
```

> **코드 수정 후 재배포:**
> ```bash
> docker build -t aws-resource-scanner-api:latest ./api
> kind load docker-image aws-resource-scanner-api:latest --name <클러스터명>
> kubectl rollout restart deployment/api-server -n ai-media
> ```

### 5단계: K8s 매니페스트 적용

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/api.yaml
kubectl apply -f k8s/n8n.yaml
```

### 6단계: n8n 워크플로우 설정 (최초 1회)

1. n8n UI 포트포워딩:
   ```bash
   kubectl port-forward svc/n8n-service -n ai-media 5678:5678
   ```
2. `http://localhost:5678` 접속
3. `n8n-workflows/aws_resource_diet.json` Import
4. **Gemini API 키** 및 **Telegram Bot Credentials**, **Chat ID** 입력
5. 워크플로우 **Publish** (활성화)

### 7단계: 동작 확인

```bash
# API 포트포워딩
kubectl port-forward svc/api-service -n ai-media 8080:80

# 스캔 결과 확인
curl http://localhost:8080/aws-waste | python3 -m json.tool
```
