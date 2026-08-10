# Worker 問題排除指南

## 📋 常見問題與解決方案

本文檔收錄了開發和部署 Worker 時常見的錯誤與解決方案。

---

## 🔍 診斷流程

```
問題發生
    │
    ▼
1. 檢查日誌 (docker-compose logs -f <service>)
    │
    ▼
2. 檢查服務狀態 (docker-compose ps)
    │
    ▼
3. 檢查網路連線 (docker exec <container> ping <host>)
    │
    ▼
4. 檢查環境變數 (docker exec <container> env)
    │
    ▼
5. 檢查資料庫狀態 (docker exec postgres psql)
```

---

## 🚨 Worker 相關問題

### 1. Worker 無法註冊

**症狀**: 
```
Error: 409 Conflict - Worker 'llm-01' already exists
```

**原因**: Worker ID 已被使用

**解決方案**:
```python
# 方案 1: 使用不同的 WORKER_ID
export WORKER_ID="llm-02"

# 方案 2: 刪除舊的 Worker 記錄
docker exec -it anime-postgres psql -U anime -d anime -c "DELETE FROM workers WHERE id='llm-01';"
```

---

### 2. Worker 無法連線到 API

**症狀**:
```
requests.exceptions.ConnectionError: HTTPConnectionPool(host='localhost', port=8000)
```

**原因**: 
- API 服務未啟動
- 網路配置錯誤
- 容器間無法通訊

**解決方案**:
```powershell
# 1. 檢查 API 是否運行
docker-compose ps api

# 2. 檢查 API 健康狀態
curl http://localhost:8000/health

# 3. 在容器內測試連線
docker exec anime-worker-agent ping api
docker exec anime-worker-agent curl http://api:8000/health

# 4. 修正環境變數 (如果在容器內)
# 將 API_BASE_URL 改為 http://api:8000 而不是 http://localhost:8000
```

**正確的 docker-compose.yml 配置**:
```yaml
worker-agent:
  environment:
    API_BASE_URL: http://api:8000  # 使用服務名稱，不是 localhost
```

---

### 3. Worker 無法領取作業

**症狀**:
```
No available jobs
```

**原因**:
- 作業佇列為空
- Worker 能力不匹配
- 作業已被其他 Worker 領取

**解決方案**:
```powershell
# 1. 檢查作業佇列
curl http://localhost:8000/projects/{project_id}/jobs

# 2. 檢查 Worker 能力
curl http://localhost:8000/workers | findstr capabilities

# 3. 確認 Worker 的 capabilities 包含作業類型
# 例如: character_analysis, story_generation
```

**檢查 Worker 能力匹配**:
```python
# 在 API 端檢查
def claim_job(worker_id: str) -> Job | None:
    worker = db.get(Worker, worker_id)
    
    # 找出佇列中的作業
    jobs = db.scalars(
        select(Job)
        .where(Job.status == "queued")
        .order_by(Job.priority.asc(), Job.created_at.asc())
    ).all()
    
    for job in jobs:
        # 檢查能力匹配
        if job.job_type in worker.capabilities:
            return job
    
    return None  # 沒有匹配的作業
```

---

### 4. Worker 心跳逾時

**症狀**:
```
Worker 'llm-01' marked as offline (no heartbeat for 60s)
```

**原因**:
- Worker 程序崩潰
- 網路中斷
- Worker 負載過高

**解決方案**:
```powershell
# 1. 檢查 Worker 程序
docker-compose ps worker-agent

# 2. 查看 Worker 日誌
docker-compose logs --tail=100 worker-agent

# 3. 重啟 Worker
docker-compose restart worker-agent

# 4. 檢查 CPU/記憶體使用率
docker stats worker-agent
```

**調整心跳逾時時間**:
```python
# 在 orchestrator 中調整
HEARTBEAT_TIMEOUT_SECONDS = int(os.getenv("HEARTBEAT_TIMEOUT_SECONDS", "60"))
```

---

### 5. 作業執行失敗

**症狀**:
```
Job 'job_123' failed: Maximum retries exceeded
```

**原因**:
- LLM API 錯誤
- 網路問題
- 輸入資料格式錯誤

**解決方案**:
```powershell
# 1. 查看作業錯誤訊息
curl http://localhost:8000/projects/{project_id}/jobs | python -m json.tool

# 2. 檢查錯誤詳細資訊
docker exec -it anime-postgres psql -U anime -d anime -c "SELECT id, job_type, error, attempt, max_attempts FROM jobs WHERE status='failed';"

# 3. 手動重試作業
docker exec -it anime-postgres psql -U anime -d anime -c "UPDATE jobs SET status='queued', worker_id=NULL WHERE id='job_123' AND attempt < max_attempts;"
```

**增加重試次數**:
```python
# 在建立作業時
max_attempts = int(os.getenv("MAX_JOB_ATTEMPTS", "5"))  # 預設 3，改為 5
```

---

## 🗄️ 資料庫相關問題

### 1. PostgreSQL 連線失敗

**症狀**:
```
sqlalchemy.exc.OperationalError: connection refused
```

**解決方案**:
```powershell
# 1. 檢查 PostgreSQL 狀態
docker-compose ps postgres

# 2. 檢查 PostgreSQL 日誌
docker-compose logs postgres

# 3. 測試連線
docker exec -it anime-postgres pg_isready -U anime -d anime

# 4. 檢查環境變數
docker-compose exec api env | grep DATABASE_URL
```

**正確的 DATABASE_URL 格式**:
```
postgresql+psycopg://anime:anime_password@postgres:5432/anime
```

---

### 2. 資料表不存在

**症狀**:
```
sqlalchemy.exc.ProgrammingError: relation "workers" does not exist
```

**解決方案**:
```powershell
# 1. 檢查 migrations 是否執行
docker exec -it anime-postgres psql -U anime -d anime -c "\dt"

# 2. 手動執行 migrations
docker exec -i anime-postgres psql -U anime -d anime < /docker-entrypoint-initdb.d/001_worker_protocol.sql
docker exec -i anime-postgres psql -U anime -d anime < /docker-entrypoint-initdb.d/002_control_plane.sql

# 3. 或重建資料庫容器
docker-compose down -v
docker-compose up -d postgres
```

---

## 💾 Redis 相關問題

### 1. Redis 連線失敗

**症狀**:
```
redis.exceptions.ConnectionError: Connection refused
```

**解決方案**:
```powershell
# 1. 檢查 Redis 狀態
docker-compose ps redis

# 2. 測試連線
docker exec -it anime-redis redis-cli ping

# 3. 檢查環境變數
docker-compose exec api env | grep REDIS_URL
```

**正確的 REDIS_URL 格式**:
```
redis://redis:6379/0
```

---

## 📦 MinIO 相關問題

### 1. MinIO 連線失敗

**症狀**:
```
minio.error.S3Error: Connection refused
```

**解決方案**:
```powershell
# 1. 檢查 MinIO 狀態
docker-compose ps minio

# 2. 測試連線
curl http://localhost:9000/minio/health/live

# 3. 檢查環境變數
docker-compose exec api env | grep S3_
```

**正確的環境變數**:
```env
S3_ENDPOINT=http://minio:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin123
```

---

### 2. 圖片上傳失敗

**症狀**:
```
minio.error.S3Error: The specified bucket does not exist
```

**解決方案**:
```powershell
# 1. 手動建立 bucket
docker exec -it anime-minio mc alias set local http://localhost:9000 minioadmin minioadmin123
docker exec -it anime-minio mc mb local/assets

# 2. 設定公開存取
docker exec -it anime-minio mc anonymous set public local/assets

# 3. 或在程式碼中自動建立
# (已在 upload_to_s3 函式中處理)
```

---

## 🤖 LLM Worker 特定問題

### 1. OpenAI API 錯誤

**症狀**:
```
openai.APIConnectionError: Connection error
```

**解決方案**:
```powershell
# 1. 檢查 API Key
docker-compose exec worker-agent env | grep OPENAI_API_KEY

# 2. 測試 API 連線
curl https://api.openai.com/v1/models `
  -H "Authorization: Bearer your-api-key"

# 3. 檢查配額
# 前往 https://platform.openai.com/account/usage
```

**正確的環境變數**:
```env
OPENAI_API_KEY=sk-your-api-key-here
LLM_MODEL=gpt-4o
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=0.7
```

---

### 2. JSON 解析錯誤

**症狀**:
```
json.JSONDecodeError: Expecting value: line 1 column 1
```

**原因**: LLM 回傳的不是有效 JSON

**解決方案**:
```python
def parse_json_response(response: str) -> dict:
    """安全解析 JSON 回應"""
    import json
    import re
    
    # 嘗試直接解析
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    
    # 嘗試提取 JSON 區塊
    json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # 嘗試提取 {} 區塊
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    
    raise ValueError(f"Cannot parse JSON from response: {response[:200]}")
```

---

## 🎨 GPU Worker 特定問題

### 1. CUDA 裝置不可用

**症狀**:
```
torch.cuda.is_available() = False
```

**解決方案**:
```powershell
# 1. 檢查 NVIDIA 驅動
nvidia-smi

# 2. 檢查 CUDA 版本
nvcc --version

# 3. 檢查 Docker 是否有 NVIDIA 支援
docker run --runtime=nvidia --rm nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi

# 4. 安裝 NVIDIA Container Toolkit
# 參考: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html
```

**正確的 docker-compose.yml 配置**:
```yaml
worker-gpu:
  runtime: nvidia
  environment:
    - NVIDIA_VISIBLE_DEVICES=all
    - CUDA_VISIBLE_DEVICES=0
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

---

### 2. VRAM 不足

**症狀**:
```
torch.cuda.OutOfMemoryError: CUDA out of memory
```

**解決方案**:
```python
# 1. 清理 GPU 快取
torch.cuda.empty_cache()

# 2. 使用更小的批次大小
batch_size = 1  # 而不是 4

# 3. 使用模型量化
pipe = StableDiffusionPipeline.from_pretrained(
    model_name,
    load_in_4bit=True  # 4-bit 量化
)

# 4. 使用 CPU 離載
pipe.enable_model_cpu_offload()

# 5. 使用 xFormers
pipe.enable_xformers_memory_efficient_attention()
```

**監控 VRAM 使用**:
```powershell
# 即時監控
watch -n 1 nvidia-smi

# 或在 Python 中
import torch
print(f"VRAM Total: {torch.cuda.get_device_properties(0).total_memory / 1024**2:.0f} MB")
print(f"VRAM Used: {torch.cuda.memory_allocated(0) / 1024**2:.0f} MB")
```

---

## 📊 效能問題

### 1. Worker 處理速度慢

**診斷步驟**:
```powershell
# 1. 檢查 CPU 使用率
docker stats worker-agent

# 2. 檢查網路延遲
docker exec worker-agent ping api

# 3. 檢查 LLM API 回應時間
# 在程式碼中加入計時
import time
start = time.time()
result = call_llm(prompt)
print(f"LLM API took {time.time() - start:.2f}s")
```

**最佳化建議**:
- 使用更快的 LLM 模型 (gpt-4o 比 gpt-4-turbo 快)
- 減少 max_tokens
- 使用快取重複的 prompt
- 增加 Worker 數量 (水平擴展)

---

### 2. 資料庫查詢慢

**診斷步驟**:
```sql
-- 檢查慢查詢
SELECT query, calls, total_time, mean_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;

-- 檢查索引
\d+ jobs
```

**最佳化建議**:
```sql
-- 為常用查詢建立索引
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_project_id ON jobs(project_id);
CREATE INDEX idx_jobs_worker_type ON jobs(worker_type);
```

---

## 🔧 除錯工具

### 1. 啟用詳細日誌

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### 2. 使用 Python Debugger

```python
import pdb; pdb.set_trace()  # 在程式碼中設定中斷點
```

### 3. 監控 Docker 資源

```powershell
# 查看所有容器資源使用
docker stats

# 查看特定容器
docker stats worker-agent
```

---

## 📞 尋求幫助

如果以上解決方案無法解決你的問題:

1. **檢查文件**: 重新閱讀相關的 Worker 開發指南
2. **查看日誌**: 收集完整的錯誤日誌
3. **建立 Issue**: 在 GitHub 建立 Issue，包含:
   - 問題描述
   - 錯誤日誌
   - 環境資訊 (Docker 版本、Python 版本等)
   - 重現步驟

---

**版本**: 1.0.0  
**最後更新**: 2026-08-10
