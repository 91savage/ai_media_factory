# AI Media Factory

텍스트 프롬프트를 받아 비동기적으로 이미지를 생성하고 Telegram 알림을 보내는 이벤트 주도(Event-Driven) 마이크로서비스 파이프라인. K8s의 오케스트레이션과 n8n의 워크플로우를 결합한 시스템입니다.

## 아키텍처 개요
1. **API Server (FastAPI)**: 사용자의 텍스트 프롬프트를 수신하고 작업 ID를 부여하여 Redis 큐에 넣습니다(Push).
2. **Message Queue (Redis)**: 비동기 작업 처리를 위한 메시지 브로커 역할을 수행합니다.
3. **AI Worker (Python)**: 큐를 모니터링하다가 작업이 들어오면 꺼내어 처리하고(현재는 5초 지연 시뮬레이터 적용), 완성된 결과(가짜 이미지 URL)를 Webhook으로 쏩니다.
4. **n8n Workflow**: Worker가 발송한 처리 결과를 Webhook으로 받아 Telegram 등으로 메시지를 발송하는 후처리(배송)를 담당합니다.

## 시스템 요구사항
- Docker
- Kubernetes 클러스터 (e.g., Kind, Minikube 등)
- `kubectl` 커맨드라인 툴

## 배포 및 실행 가이드 (Local K8s 환경)

### 1단계: 도커 이미지 빌드 및 K8s 로드
```bash
# API Server 이미지 빌드 및 로드
docker build -t ai-media-api:latest ./api
kind load docker-image ai-media-api:latest --name <클러스터명>

# AI Worker 이미지 빌드 및 로드
docker build -t ai-media-worker:latest ./worker
kind load docker-image ai-media-worker:latest --name <클러스터명>
```

### 2단계: K8s 매니페스트 적용
```bash
# 네임스페이스 및 Redis 배포
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/redis.yaml

# API, Worker, n8n 배포
kubectl apply -f k8s/api.yaml
kubectl apply -f k8s/worker.yaml
kubectl apply -f k8s/n8n.yaml
```

### 3단계: n8n 워크플로우 셋팅 (최초 1회)
1. n8n UI 포트포워딩 실행:
   ```bash
   kubectl port-forward svc/n8n-service -n ai-media 5678:5678
   ```
2. 웹 브라우저(`http://localhost:5678`)에 접속합니다.
3. 레포지토리에 포함된 `n8n-workflows/telegram_notification.json` 파일을 n8n 화면에 Import(오른쪽 위 메뉴 > Import from File 등) 합니다.
4. **Telegram 노드** 내부 설정에 들어가 본인의 **Telegram Bot Credentials** 정보와 **Chat ID**를 기입합니다.
5. 설정 완료 후 웹 에디터 우측 상단의 **`Publish` 버튼**을 꼭 켜서 워크플로우를 활성화합니다.

### 4단계: 테스트 로직 수행
1. API 포트포워딩 실행:
   ```bash
   kubectl port-forward svc/api-service -n ai-media 8000:80
   ```
2. 이미지 생성 요청 발송 (웹 브라우저에서 `http://localhost:8000` 직접 접속 또는 curl 이용):
   ```bash
   curl -X POST "http://localhost:8000/generate-image?prompt=dog_playing_in_park"
   ```
3. Telegram으로 알림이 오는지 최종 확인!

### 5단계: Telegram ChatOps 테스트 준비 (Phase 4.2 전용)
텔레그램 봇과 양방향 통신(ChatOps)을 구축하려면 텔레그램 서버가 우리 로컬 n8n으로 웹훅을 쏠 수 있어야 합니다. 텔레그램 정책상 **반드시 HTTPS 주소가 필요**하므로 `localtunnel`을 사용해 포트를 외부로 뚫어주어야 합니다.

> **💡 필수 전제조건 (Port-Forwarding):**
> localtunnel은 우리 PC(Mac)의 5678번 포트를 인터넷과 이어줄 뿐입니다. 따라서 터널을 뚫기 전에 **반드시 다른 터미널 창에서 K8s n8n 포트포워딩이 살아서 유지되고 있어야** 통신이 전달됩니다!
> ```bash
> kubectl port-forward svc/n8n-service -n ai-media 5678:5678
> ```

1. **새로운 터미널 탭**을 하나 더 열어, 해당 5678 포트를 HTTPS로 터널링하는 백그라운드 명령어를 실행합니다.
   ```bash
   # npx 설치 동의(y) 메시지가 보이지 않도록 --yes 옵션을 추가합니다.
   npx --yes localtunnel --port 5678 > localtunnel.log 2>&1 &
   ```
2. 생성된 HTTPS 주소를 확인합니다.
3. 발급받은 `https://...` 주소를 복사합니다.
4. `k8s/n8n.yaml` 파일을 열고, `env` 섹션의 `WEBHOOK_URL` 값을 복사한 주소로 변경합니다.
   ```yaml
           - name: WEBHOOK_URL
             value: "https://blue-lizards-poke.loca.lt" # 여기에 붙여넣기
   ```
5. 변경된 K8s 설정을 n8n.yaml에 적용하고 n8n 파드를 재시작합니다.
   ```bash
   kubectl apply -f k8s/n8n.yaml
   kubectl rollout restart deployment n8n -n ai-media
   ```
6. `http://localhost:5678` 로 n8n에 접속한 뒤, `n8n-workflows/telegram_chatops.json` 워크플로우를 Publish(활성화)하고 텔레그램 봇에게 채팅을 걸어 테스트합니다.
   - **⚠️ 중요 주의사항 (Webhook 재등록):** 만약 터널을 껐다 켜서 URL이 바뀌었거나 봇이 메세지에 응답하지 않는다면, 현재 켜져 있는 **[Active] / Publish 스위치를 한 번 껐다가 2초 뒤 다시 켜주세요.** 껐다 켜는 순간 n8n이 텔레그램 서버로 바뀐 Webhook URL을 자동으로 재전송(업데이트)합니다.
