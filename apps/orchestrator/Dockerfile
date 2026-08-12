FROM python:3.11-slim

WORKDIR /app

# 確保 Docker 中 Python 輸出即時刷新
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 使用 -u 標記讓 Python 輸出即時刷新
CMD ["python", "-u", "main.py"]
