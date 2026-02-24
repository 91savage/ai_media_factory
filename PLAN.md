# AI 미디어 팩토리 구축 Plan (K8s + n8n)

**프로젝트 개요:**
텍스트 프롬프트를 받아 비동기적으로 이미지를 생성하고 알림을 보내는 이벤트 주도(Event-Driven) 마이크로서비스 아키텍처. K8s의 오케스트레이션 능력과 n8n의 워크플로우 자동화를 결합.

---
### 📍 Phase 1: 기반 인프라 배포 (API 서버 & 메세지 큐) - [현재 진행 단계]
1.  **[현재 대기 중]** 앞서 만든 API 서버(FastAPI) 코드를 Docker 이미지로 빌드합니다 (`ai-media-api:latest`).
2.  빌드한 이미지를 로컬 K8s 클러스터(`k8s-study-control-plane`) 내부로 로드합니다 (예: `kind load docker-image ...`).
3.  준비해 둔 YAML 파일들(`k8s/namespace.yaml`, `k8s/redis.yaml`, `k8s/api.yaml`)을 K8s에 배포(`kubectl apply`)합니다.
4.  API 서버 포트포워딩 후 테스트 프롬프트를 날려보고, Redis 큐에 정상적으로 적재되는지 확인합니다.

### 📍 Phase 2: AI Worker(공장 노동자) 구축
1.  Redis 큐를 계속 폴링(Polling)하다가 작업이 들어오면 가져와서 "이미지 생성" 로직을 처리하는 Worker 코드(Python)를 작성합니다. (우선은 5초 대기 후 가짜 이미지 URL을 반환하는 시뮬레이터로 구현)
2.  Worker 코드를 Docker 이미지로 빌드하고, K8s 클러스터에 로드합니다.
3.  Worker를 위한 K8s Deployment 매니페스트(`k8s/worker.yaml`)를 작성하고 배포합니다.
4.  (옵션) HPA(Horizontal Pod Autoscaler) 설정을 추가하여 큐에 작업이 쌓일 때 Worker Pod 개수가 자동으로 스케일 아웃되는지 테스트합니다.

### 📍 Phase 3: n8n 워크플로우 연동 (배송/알림)
1.  K8s 클러스터 내부에 n8n을 배포합니다 (Helm 또는 매니페스트 활용).
2.  n8n UI에 접속하여 Webhook 노드를 생성하고 고유 URL을 발급받습니다.
3.  Phase 2의 Worker 코드를 수정하여, 작업 완료 시 생성된 결과물(URL 등)을 n8n Webhook으로 HTTP POST 요청하도록 합니다.
4.  n8n에서 결과를 받아 Slack이나 이메일 등으로 "이미지 생성이 완료되었습니다" 알림을 쏘는 파이프라인(ChatOps)을 완성합니다.



