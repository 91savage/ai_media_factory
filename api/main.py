from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import FileResponse
import redis
import uuid
import os

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
