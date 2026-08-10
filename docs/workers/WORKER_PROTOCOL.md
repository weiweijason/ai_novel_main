# Worker 通訊協定 - 詳細說明

## 📋 概述

本文檔定義了 AI 動漫工作室中 Worker 與 API 服務之間的通訊協定，包含所有 API 端點、請求/回應格式、錯誤處理和狀態碼。

## 🌐 API 端點總覽

| 端點 | 方法 | 說明 |
|------|------|------|
| `/worker/register` | POST | Worker 註冊 |
| `/worker/heartbeat` | POST | 心跳回報 |
| `/worker/jobs/claim` | POST | 領取作業 |
| `/worker/jobs/{job_id}/status` | POST | 更新作業狀態 |
| `/workers` | GET | 列出所有 Worker |
| `/projects/{project_id}/jobs` | GET | 列出專案作業 |

## 📡 詳細協定說明

### 1. Worker 註冊

#### 請求

```http
POST /worker/register
Content-Type: application/json
```

```json
{
  "worker_id": "llm-01",
  "worker_type": "llm",
  "hostname": "worker-hostname",
  "capabilities": ["character_analysis", "story_generation"],
  "models": ["gpt-4o"],
  "gpu": {
    "name": "NVIDIA A100",
    "vram_total": 80000
  }
}
```

| 欄位 | 類型 | 必填 | 說明 |
|------|------|------|------|
| `worker_id` | string | ✅ | Worker 唯一識別碼 |
| `worker_type` | string | ✅ | Worker 類型 (`llm`, `gpu`, `audio`) |
| `hostname` | string | ❌ | Worker 主機名稱 |
| `capabilities` | string[] | ✅ | 支援的作業類型列表 |
| `models` | string[] | ❌ | 安裝的模型列表 |
| `gpu` | object | ❌ | GPU 資訊 (僅 GPU Worker) |

#### 回應

**成功 (200 OK)**
```json
{
  "worker_id": "llm-01",
  "worker_type": "llm",
  "status": "registered",
  "registered_at": "2026-08-10T12:00:00Z"
}
```

**錯誤 (409 Conflict)**
```json
{
  "detail": "Worker 'llm-01' already exists"
}
```

**錯誤 (422 Unprocessable Entity)**
```json
{
  "detail": [
    {
      "loc": ["body", "worker_type"],
      "msg": "value is not a valid enumeration member",
      "type": "type_error.enum"
    }
  ]
}
```

---

### 2. 心跳回報

#### 請求

```http
POST /worker/heartbeat
Content-Type: application/json
```

```json
{
  "worker_id": "llm-01",
  "status": "busy",
  "current_job": "job_123",
  "gpu": {
    "name": "NVIDIA A100",
    "vram_total": 80000,
    "vram_used": 45000
  }
}
```

| 欄位 | 類型 | 必填 | 說明 |
|------|------|------|------|
| `worker_id` | string | ✅ | Worker 識別碼 |
| `status` | string | ✅ | 當前狀態 (`idle`, `busy`, `error`) |
| `current_job` | string | ❌ | 正在執行的作業 ID |
| `gpu` | object | ❌ | GPU 狀態資訊 |

#### 回應

**成功 (200 OK)**
```json
{
  "worker_id": "llm-01",
  "status": "busy",
  "last_heartbeat": "2026-08-10T12:05:00Z"
}
```

**錯誤 (404 Not Found)**
```json
{
  "detail": "Worker 'llm-01' not found"
}
```

---

### 3. 領取作業

#### 請求

```http
POST /worker/jobs/claim
Content-Type: application/json
```

```json
{
  "worker_id": "llm-01"
}
```

#### 回應

**成功 (200 OK)**
```json
{
  "id": "job_abc123",
  "type": "character_analysis",
  "project_id": "project_xyz789",
  "episode_id": "episode_001",
  "scene_id": null,
  "input": {
    "brief": "一位勇敢的女劍士",
    "project_name": "我的動漫故事"
  },
  "priority": 2,
  "max_attempts": 3,
  "created_at": "2026-08-10T12:00:00Z"
}
```

**沒有可用作業 (404 Not Found)**
```json
{
  "detail": "No available jobs"
}
```

**錯誤 (404 Not Found)**
```json
{
  "detail": "Worker 'llm-01' not found"
}
```

#### 作業領取邏輯

1. **優先級排序**: 優先領取 `priority` 值較低的作業 (1 最高)
2. **能力匹配**: 只領取 Worker `capabilities` 中包含的作業類型
3. **鎖定機制**: 領取後作業狀態變為 `running`，其他 Worker 無法領取
4. **公平性**: 同優先級的作業按建立時間排序 (FIFO)

---

### 4. 更新作業狀態

#### 請求

```http
POST /worker/jobs/{job_id}/status
Content-Type: application/json
```

```json
{
  "status": "completed",
  "progress": 1.0,
  "result": {
    "name": "艾莉亞",
    "personality": { ... },
    "appearance": { ... }
  },
  "error": null
}
```

| 欄位 | 類型 | 必填 | 說明 |
|------|------|------|------|
| `status` | string | ✅ | 新狀態 (`running`, `completed`, `failed`) |
| `progress` | float | ❌ | 完成進度 (0.0 - 1.0) |
| `result` | object | ❌ | 作業結果 (完成時必填) |
| `error` | string | ❌ | 錯誤訊息 (失敗時必填) |

#### 回應

**成功 (200 OK)**
```json
{
  "job_id": "job_abc123",
  "status": "completed",
  "updated_at": "2026-08-10T12:10:00Z"
}
```

**錯誤 (404 Not Found)**
```json
{
  "detail": "Job 'job_abc123' not found"
}
```

**錯誤 (409 Conflict)**
```json
{
  "detail": "Job is not assigned to this worker"
}
```

**錯誤 (422 Unprocessable Entity)**
```json
{
  "detail": [
    {
      "loc": ["body", "result"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

#### 狀態轉換規則

```
queued ──► running ──► completed
                │
                └──► failed ──► queued (重試)
```

| 當前狀態 | 允許轉換到 | 說明 |
|---------|-----------|------|
| `queued` | `running` | Worker 開始執行 |
| `running` | `completed` | 作業成功完成 |
| `running` | `failed` | 作業執行失敗 |
| `failed` | `queued` | Orchestrator 重試 |

---

### 5. 列出所有 Worker

#### 請求

```http
GET /workers
```

#### 回應

**成功 (200 OK)**
```json
[
  {
    "id": "llm-01",
    "worker_type": "llm",
    "hostname": "llm-worker-host",
    "status": "busy",
    "capabilities": ["character_analysis", "story_generation"],
    "models": ["gpt-4o"],
    "current_job": "job_123",
    "last_heartbeat": "2026-08-10T12:05:00Z",
    "created_at": "2026-08-10T10:00:00Z"
  },
  {
    "id": "gpu-01",
    "worker_type": "gpu",
    "hostname": "gpu-worker-host",
    "status": "idle",
    "capabilities": ["character_image_gen", "scene_image_gen"],
    "models": ["stable-diffusion-xl"],
    "gpu": "NVIDIA A100",
    "vram": 80000,
    "current_job": null,
    "last_heartbeat": "2026-08-10T12:04:00Z",
    "created_at": "2026-08-10T10:00:00Z"
  }
]
```

---

### 6. 列出專案作業

#### 請求

```http
GET /projects/{project_id}/jobs
```

#### 回應

**成功 (200 OK)**
```json
[
  {
    "id": "job_abc123",
    "job_type": "character_analysis",
    "worker_type": "llm",
    "status": "completed",
    "attempt": 1,
    "max_attempts": 3,
    "created_at": "2026-08-10T12:00:00Z",
    "started_at": "2026-08-10T12:01:00Z",
    "completed_at": "2026-08-10T12:05:00Z"
  },
  {
    "id": "job_def456",
    "job_type": "story_generation",
    "worker_type": "llm",
    "status": "running",
    "attempt": 1,
    "max_attempts": 3,
    "created_at": "2026-08-10T12:05:30Z",
    "started_at": "2026-08-10T12:06:00Z",
    "completed_at": null
  }
]
```

---

## ⚠️ 錯誤處理

### HTTP 狀態碼

| 狀態碼 | 說明 | 常見原因 |
|--------|------|---------|
| 200 | 成功 | 請求成功處理 |
| 400 | 錯誤請求 | 請求格式錯誤 |
| 401 | 未授權 | 認證失敗 |
| 404 | 找不到 | Worker 或作業不存在 |
| 409 | 衝突 | Worker ID 已存在、作業狀態衝突 |
| 422 | 無法處理 | 驗證失敗 |
| 500 | 伺服器錯誤 | 內部錯誤 |

### 錯誤回應格式

```json
{
  "detail": "錯誤訊息描述"
}
```

或驗證錯誤:

```json
{
  "detail": [
    {
      "loc": ["body", "field_name"],
      "msg": "錯誤描述",
      "type": "error_type"
    }
  ]
}
```

---

## 🔐 安全性

### 認證機制

目前版本使用簡單的 API Key 認證:

```http
POST /worker/register
Content-Type: application/json
X-API-Key: your-secret-api-key
```

### 建議的安全措施

1. **TLS/SSL**: 生產環境應使用 HTTPS
2. **API Key 輪換**: 定期更換 API Key
3. **IP 白名單**: 限制 Worker 來源 IP
4. **速率限制**: 防止過多的請求

---

## 📊 監控與日誌

### Worker 健康檢查

Orchestrator 會監控 Worker 的心跳:

- **逾時時間**: 30 秒無心跳視為離線
- **狀態更新**: 離線 Worker 的作業會被重新分配
- **警報**: 連續 3 次心跳失敗觸發警報

### 日誌格式

```json
{
  "timestamp": "2026-08-10T12:00:00Z",
  "level": "INFO",
  "worker_id": "llm-01",
  "event": "job_claimed",
  "job_id": "job_123",
  "details": {
    "job_type": "character_analysis",
    "project_id": "project_xyz"
  }
}
```

---

## 🧪 測試工具

### cURL 測試範例

```bash
# 註冊 Worker
curl -X POST http://localhost:8000/worker/register \
  -H "Content-Type: application/json" \
  -d '{
    "worker_id": "test-llm-01",
    "worker_type": "llm",
    "hostname": "test-host",
    "capabilities": ["character_analysis"],
    "models": ["gpt-4o"]
  }'

# 心跳回報
curl -X POST http://localhost:8000/worker/heartbeat \
  -H "Content-Type: application/json" \
  -d '{
    "worker_id": "test-llm-01",
    "status": "idle",
    "current_job": null
  }'

# 領取作業
curl -X POST http://localhost:8000/worker/jobs/claim \
  -H "Content-Type: application/json" \
  -d '{
    "worker_id": "test-llm-01"
  }'

# 更新作業狀態
curl -X POST http://localhost:8000/worker/jobs/job_123/status \
  -H "Content-Type: application/json" \
  -d '{
    "status": "completed",
    "progress": 1.0,
    "result": {
      "name": "測試角色",
      "personality": {},
      "appearance": {}
    }
  }'
```

### Python 測試腳本

```python
import requests

API_BASE = "http://localhost:8000"

def test_register():
    response = requests.post(f"{API_BASE}/worker/register", json={
        "worker_id": "test-worker",
        "worker_type": "llm",
        "hostname": "test-host",
        "capabilities": ["character_analysis"],
        "models": ["gpt-4o"]
    })
    print(f"Register: {response.status_code}")
    print(response.json())

def test_heartbeat():
    response = requests.post(f"{API_BASE}/worker/heartbeat", json={
        "worker_id": "test-worker",
        "status": "idle",
        "current_job": None
    })
    print(f"Heartbeat: {response.status_code}")
    print(response.json())

if __name__ == "__main__":
    test_register()
    test_heartbeat()
```

---

## 📚 相關文件

- [Worker 架構總覽](./ARCHITECTURE.md)
- [Orchestrator 開發指南](./ORCHESTRATOR.md)
- [LLM Worker 開發指南](./LLM_WORKER.md)
- [GPU Worker 開發指南](./GPU_WORKER.md)

---

**版本**: 1.0.0  
**最後更新**: 2026-08-10
