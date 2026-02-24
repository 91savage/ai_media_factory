from fastapi import FastAPI, BackgroundTasks
import redis
import uuid
import os

app = FastAPI(title="AI Media Factory API")

# Redis 연결
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

@app.post("/generate-image")
async def generate_image(prompt: str):
    """사용자로부터 텍스트 프롬프트를 받아 이미지 생성 작업을 큐에 넣습니다."""
    task_id = str(uuid.uuid4())
    
    # 큐에 작업 넣기 (List 사용: 'image_queue')
    task_payload = f"{task_id}::{prompt}"
    r.lpush("image_queue", task_payload)
    
    return {
        "status": "접수 완료", 
        "task_id": task_id, 
        "message": "이미지 생성 작업이 대기열에 추가되었습니다."
    }

@app.get("/health")
def health_check():
    return {"status": "ok"}
