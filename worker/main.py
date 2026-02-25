import redis
import os
import time
import requests

# Redis 설정
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
QUEUE_NAME = "image_queue"

# n8n Webhook 설정
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")

# Redis 연결
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

import json

def process_image_generation():
    print(f"[*] AI Worker 시작. '{QUEUE_NAME}' 큐 대기 중...", flush=True)
    
    while True:
        try:
            result = r.blpop(QUEUE_NAME, timeout=0)
            
            if result:
                _, payload = result
                
                # JSON 파싱으로 로직 보강
                try:
                    task_data = json.loads(payload.decode('utf-8'))
                    task_id = task_data.get("task_id", "unknown_id")
                    prompt = task_data.get("prompt", "No prompt")
                    chat_id = task_data.get("chat_id")
                except json.JSONDecodeError:
                    # 기존 레거시 문자열(test::prompt) 대비용 안전 장치
                    payload_str = payload.decode('utf-8')
                    if "::" in payload_str:
                        task_id, prompt = payload_str.split("::", 1)
                    else:
                        task_id, prompt = "unknown", payload_str
                    chat_id = None
                
                print(f"\n[+] 작업 수신됨!")
                print(f"    - Task ID: {task_id}")
                print(f"    - Prompt: {prompt}")
                if chat_id:
                    print(f"    - Chat ID: {chat_id}")
                
                print(f"    - ⏳ 시뮬레이션: 이미지 생성 중... (5초 대기)")
                time.sleep(5)
                
                mock_image_url = f"https://mock-image-factory.com/{task_id}.png"
                
                print(f"    - ✅ 이미지 생성 완료!")
                print(f"    - Result URL: {mock_image_url}")
                
                # 4. n8n으로 결과 전송 로직 추가
                if N8N_WEBHOOK_URL:
                    try:
                        n8n_payload = {
                            "task_id": task_id, 
                            "prompt": prompt, 
                            "image_url": mock_image_url,
                            "chat_id": chat_id
                        }
                        resp = requests.post(N8N_WEBHOOK_URL, json=n8n_payload, timeout=5)
                        print(f"    - 🚀 n8n Webhook 전송 완료 (Status: {resp.status_code})")
                    except Exception as req_e:
                        print(f"    - 🚨 n8n 전송 실패: {req_e}")
                
                print("-" * 40, flush=True)
                
        except Exception as e:
            print(f"[!] 에러 발생: {e}", flush=True)
            time.sleep(2)

if __name__ == "__main__":
    process_image_generation()
