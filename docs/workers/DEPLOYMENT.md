# Worker 部署指南

## 🚀 生產環境部署

本指南說明如何在生產環境中部署和擴展 Worker。

---

## 📋 部署前檢查清單

### 基礎設施

- [ ] Docker 與 Docker Compose 已安裝
- [ ] PostgreSQL 16 已部署
- [ ] Redis 7 已部署
- [ ] MinIO 或 AWS S3 已部署
- [ ] 防火牆規則已配置

### 環境變數

- [ ] `DATABASE_URL` 已設定
- [ ] `REDIS_URL` 已設定
- [ ] `S3_ENDPOINT` 已設定
- [ ] `S3_ACCESS_KEY` 已設定
- [ ] `S3_SECRET_KEY` 已設定
- [ ] `OPENAI_API_KEY` 已設定 (LLM Worker)
- [ ] `WORKER_ID` 已設定 (每個 Worker 唯一)

### 安全設定

- [ ] 資料庫密碼已更改
- [ ] Redis 密碼已設定
- [ ] MinIO 存取金鑰已更改
- [ ] API 金鑰已設定
- [ ] SSL/TLS 已配置 (如果需要)

---

## 🏗️ 部署架構

### 開發環境

```
┌─────────────────────────────────────┐
│         開發工作站                   │
│                                     │
│  ┌──────┐ ┌──────────┐ ┌────────┐ │
│  │ API  │ │Orchestrator│ │Worker │ │
│  │:8000 │ │  :8001   │ │ :8002  │ │
│  └──────┘ └──────────┘ └────────┘ │
│       │         │            │     │
│  ┌────┴─────────┴────────────┴───┐ │
│  │      Docker Network           │ │
│  └───────────────────────────────┘ │
│       │         │            │     │
│  ┌────┐     ┌──────┐   ┌──────┐  │
│  │PG  │     │Redis │   │MinIO │  │
│  :5432│     │:6379 │   │:9000 │  │
│  └────┘     └──────┘   └──────┘  │
└─────────────────────────────────────┘
```

### 生產環境

```
┌──────────────────────────────────────────────────────┐
│              生產環境 (雲端/VPS)                       │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │           Load Balancer                      │   │
│  │              :443 (HTTPS)                     │   │
│  └──────────────────┬───────────────────────────┘   │
│                     │                                │
│        ┌────────────┴────────────┐                  │
│        ▼                         ▼                  │
│  ┌──────────┐            ┌──────────┐              │
│  │  API x2  │            │  API x2  │              │
│  │  :8000   │            │  :8000   │              │
│  └────┬─────┘            └────┬─────┘              │
│       │                       │                    │
│  ┌────┴───────────────────────┴────┐               │
│  │      Docker Network             │               │
│  └─────────────────────────────────┘               │
│       │         │            │         │           │
│  ┌────┐     ┌──────┐   ┌──────┐  ┌────┐          │
│  │PG  │     │Redis │   │MinIO │  │GPU │          │
│  :5432│     │:6379 │   │:9000 │  │:8002│          │
│  └────┘     └──────┘   └──────┘  └────┘          │
│                     │                              │
│              ┌──────────┐                         │
│              │LLM x3    │                         │
│              │:8002     │                         │
│              └──────────┘                         │
└──────────────────────────────────────────────────────┘
```

---

## 📦 部署步驟

### 1. 準備伺服器

```bash
# 更新系統
sudo apt update && sudo apt upgrade -y

# 安裝 Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 安裝 Docker Compose
sudo apt install docker-compose-plugin -y

# 驗證安裝
docker --version
docker compose version
```

### 2. 克隆專案

```bash
git clone https://github.com/your-org/ai-anime.git
cd ai-anime
```

### 3. 配置環境變數

```bash
# 複製範本
cp .env.example .env

# 編輯環境變數
nano .env
```

**.env 範例**:
```env
# 資料庫
DATABASE_URL=postgresql+psycopg://anime:STRONG_PASSWORD@postgres:5432/anime

# Redis
REDIS_URL=redis://:redis_password@redis:6379/0

# MinIO / S3
S3_ENDPOINT=http://minio:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=strong_minio_password
S3_BUCKET=assets

# LLM
OPENAI_API_KEY=sk-your-production-key
LLM_MODEL=gpt-4o
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=0.7

# Worker
WORKER_ID=llm-prod-01
WORKER_CAPABILITIES=character_analysis,story_generation,script_generation,scene_json_generation
WORKER_POLL_INTERVAL=5
WORKER_HEARTBEAT_INTERVAL=15

# Orchestrator
ORCHESTRATOR_INTERVAL=10
HEARTBEAT_TIMEOUT_SECONDS=60
MAX_JOB_ATTEMPTS=5
```

### 4. 啟動服務

```bash
# 啟動所有服務
docker compose up -d

# 查看狀態
docker compose ps

# 查看日誌
docker compose logs -f
```

### 5. 初始化資料庫

```bash
# 執行 migrations
docker compose exec postgres psql -U anime -d anime < migrations/001_worker_protocol.sql
docker compose exec postgres psql -U anime -d anime < migrations/002_control_plane.sql
```

### 6. 驗證部署

```bash
# 檢查 API 健康狀態
curl http://localhost:8000/health

# 檢查 Worker 註冊
curl http://localhost:8000/workers

# 建立測試專案
curl -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -d '{"name":"測試","description":"生產環境測試","source_prompt":"測試"}'
```

---

## 🔄 水平擴展

### 擴展 LLM Worker

```yaml
# docker-compose.yml
services:
  worker-llm-01:
    extends:
      file: worker-agent/docker-compose.yml
      service: worker-agent
    environment:
      WORKER_ID: llm-prod-01
      
  worker-llm-02:
    extends:
      file: worker-agent/docker-compose.yml
      service: worker-agent
    environment:
      WORKER_ID: llm-prod-02
      
  worker-llm-03:
    extends:
      file: worker-agent/docker-compose.yml
      service: worker-agent
    environment:
      WORKER_ID: llm-prod-03
```

```bash
# 啟動多個 Worker
docker compose up -d worker-llm-01 worker-llm-02 worker-llm-03
```

### 擴展 GPU Worker

```yaml
services:
  worker-gpu-01:
    build: ./worker-gpu
    runtime: nvidia
    environment:
      WORKER_ID: gpu-prod-01
      WORKER_CAPABILITIES: image_generation,video_generation
      CUDA_VISIBLE_DEVICES: 0
      
  worker-gpu-02:
    build: ./worker-gpu
    runtime: nvidia
    environment:
      WORKER_ID: gpu-prod-02
      WORKER_CAPABILITIES: image_generation,video_generation
      CUDA_VISIBLE_DEVICES: 1
```

---

## 🔒 安全最佳實踐

### 1. 使用 Docker Secrets

```yaml
# docker-compose.yml
services:
  api:
    secrets:
      - db_password
      - redis_password
      - s3_key
      - s3_secret
      - openai_key

secrets:
  db_password:
    file: ./secrets/db_password.txt
  redis_password:
    file: ./secrets/redis_password.txt
  s3_key:
    file: ./secrets/s3_key.txt
  s3_secret:
    file: ./secrets/s3_secret.txt
  openai_key:
    file: ./secrets/openai_key.txt
```

### 2. 資料庫安全

```sql
-- 建立受限的資料庫使用者
CREATE USER anime_app WITH PASSWORD 'strong_password';
GRANT CONNECT ON DATABASE anime TO anime_app;
GRANT USAGE ON SCHEMA public TO anime_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO anime_app;
```

### 3. Redis 安全

```bash
# redis.conf
requirepass strong_redis_password
bind 0.0.0.0
protected-mode yes
```

### 4. API 認證

```python
# 在 API 端點加入認證
from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader

API_KEY = os.getenv("API_KEY", "default-key-change-in-production")
api_key_header = APIKeyHeader(name="X-API-Key")

def verify_api_key(api_key: str = Depends(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

@app.post("/projects")
def create_project(project: ProjectCreate, api_key: str = Depends(verify_api_key)):
    # ...
```

---

## 📊 監控與日誌

### 1. Prometheus + Grafana

```yaml
# docker-compose.yml
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
      
  grafana:
    image: grafana/grafana:latest
    volumes:
      - grafana_data:/var/lib/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
```

**prometheus.yml**:
```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'api'
    static_configs:
      - targets: ['api:8000']
    
  - job_name: 'worker'
    static_configs:
      - targets: ['worker-agent:8002']
```

### 2. 日誌聚合

```yaml
services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.11.0
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
    volumes:
      - es_data:/usr/share/elasticsearch/data
      
  logstash:
    image: docker.elastic.co/logstash/logstash:8.11.0
    volumes:
      - ./logstash.conf:/usr/share/logstash/pipeline/logstash.conf
      
  kibana:
    image: docker.elastic.co/kibana/kibana:8.11.0
    ports:
      - "5601:5601"
```

### 3. 健康檢查

```yaml
services:
  api:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
      
  worker-agent:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8002/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

---

## 🔄 CI/CD 部署

### GitHub Actions 範例

```yaml
# .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2
        
      - name: Login to Container Registry
        uses: docker/login-action@v2
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
          
      - name: Build and push API
        uses: docker/build-push-action@v4
        with:
          context: ./apps/api
          push: true
          tags: ghcr.io/your-org/ai-anime-api:latest
          
      - name: Build and push Worker
        uses: docker/build-push-action@v4
        with:
          context: ./apps/worker-agent
          push: true
          tags: ghcr.io/your-org/ai-anime-worker:latest
          
      - name: Deploy to server
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.PROD_SERVER_HOST }}
          username: ${{ secrets.PROD_SERVER_USER }}
          key: ${{ secrets.PROD_SERVER_SSH_KEY }}
          script: |
            cd /opt/ai-anime
            docker compose pull
            docker compose up -d
            docker compose down --remove-orphans
```

---

## 📈 效能調校

### 1. 資料庫調校

```sql
-- 調整記憶體配置
ALTER SYSTEM SET shared_buffers = '2GB';
ALTER SYSTEM SET effective_cache_size = '6GB';
ALTER SYSTEM SET work_mem = '256MB';

-- 重新載入配置
SELECT pg_reload_conf();
```

### 2. Redis 調校

```bash
# redis.conf
maxmemory 2gb
maxmemory-policy allkeys-lru
```

### 3. Worker 調校

```env
# 增加併發處理
WORKER_CONCURRENCY=5

# 調整輪詢間隔
WORKER_POLL_INTERVAL=2

# 調整心跳間隔
WORKER_HEARTBEAT_INTERVAL=10
```

---

## 🚨 災難復原

### 1. 資料庫備份

```bash
# 自動備份腳本
#!/bin/bash
BACKUP_DIR="/backups/postgres"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

docker compose exec postgres pg_dump -U anime anime > "$BACKUP_DIR/anime_$TIMESTAMP.sql"

# 保留最近 7 天的備份
find $BACKUP_DIR -name "*.sql" -mtime +7 -delete
```

### 2. 資料復原

```bash
# 從備份復原
docker compose exec -i postgres psql -U anime -d anime < /backups/postgres/anime_20260810_120000.sql
```

### 3. 服務重啟

```bash
# 重啟所有服務
docker compose down
docker compose up -d

# 重啟特定服務
docker compose restart api worker-agent
```

---

**版本**: 1.0.0  
**最後更新**: 2026-08-10
