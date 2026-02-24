FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# stdout 버퍼링 방지 (로그 즉각 출력)
ENV PYTHONUNBUFFERED=1

COPY main.py .

CMD ["python", "main.py"]
