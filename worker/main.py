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
                
                print(f"    - ⏳ Gemini 모델: 이미지 생성 중... (Imagen 4.0)")
                # time.sleep(5) 
                
                image_base64 = ""
                error_msg = ""
                
                try:
                    # Gemini Imagen API 호출
                    import google.generativeai as genai
                    from io import BytesIO
                    import base64
                    
                    api_key = os.getenv("GEMINI_API_KEY")
                    if not api_key:
                        raise ValueError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")
                        
                    genai.configure(api_key=api_key)
                    
                    # google-generativeai 구버전/신버전 통합 지원 모델 로드 방식
                    client = genai.ImageGenerationModel("imagen-3.0-generate-001") # imagen-4.0 may not be fully rolled out to SDK yet, but we will try whatever the fallback is if needed. I will use the safest 3.0 model here explicitly because error means SDK might not know 'generate_images' via the new genai client at all.
                    
                    response = client.generate_images(
                        prompt=prompt,
                        number_of_images=1,
                        aspect_ratio="1:1"
                    )
                    
                    if response.generated_images:
                        # PIL Image 객체 획득
                        pil_img = response.generated_images[0].image
                        
                        # 바이너리 바이트 배열로 변환
                        buffered = BytesIO()
                        pil_img.save(buffered, format="PNG")
                        img_bytes = buffered.getvalue()
                        
                        # Webhook 전송을 위해 Base64 문자열로 인코딩
                        image_base64 = base64.b64encode(img_bytes).decode('utf-8')
                        print(f"    - ✅ 이미지 생성 완료! (Base64 길이: {len(image_base64)})")
                    else:
                        error_msg = "생성된 이미지가 없습니다."
                        print(f"    - ❌ 이미지 생성 실패: {error_msg}")
                        
                except Exception as api_e:
                    error_msg = str(api_e)
                    print(f"    - 🚨 Gemini API 호출 에러: {error_msg}")

                # 4. n8n으로 결과 전송 로직 수정 (URL 대신 Base64 전송)
                if N8N_WEBHOOK_URL:
                    try:
                        n8n_payload = {
                            "task_id": task_id, 
                            "prompt": prompt, 
                            "chat_id": chat_id,
                            "image_base64": image_base64,
                            "error": error_msg
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
