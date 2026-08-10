# Worker 快速開始指南

## 🚀 5 分鐘快速上手

本指南幫助你在 5 分鐘內啟動第一個 Worker。

---

## 前置條件

- ✅ Docker 與 Docker Compose 已安裝
- ✅ 專案基礎服務已啟動 (postgres, redis, minio, api)
- ✅ Python 3.11+ 已安裝

---

## Step 1: 啟動基礎服務

```powershell
cd d:\ai_anime

# 啟動所有基礎服務
docker-compose up -d postgres redis minio api orchestrator
```

驗證服務狀態:
```powershell
docker-compose ps
# 應該看到所有服務都是 Up 狀態
```

---

## Step 2: 啟動 Mock Worker (測試用)

專案已內建一個 Mock Worker，可以立即測試:

```powershell
# 啟動 worker-agent (使用 mock LLM)
docker-compose up -d worker-agent

# 查看日誌
docker-compose logs -f worker-agent
```

你應該看到:
```
Worker llm-01 registered successfully
Heartbeat sent: status=idle
Claiming job...
No available jobs
```

---

## Step 3: 建立測試專案

```powershell
# 建立專案
curl -X POST http://localhost:8000/projects `
  -H "Content-Type: application/json" `
  -d '{
    "name": "測試動漫",
    "description": "我的第一個測試專案",
    "source_prompt": "校園生活"
  }'
```

記錄回傳的 `project_id`，例如 `project_abc123`

---

## Step 4: 觸發工作流程

```powershell
# 觸發生成流程
curl -X POST http://localhost:8000/projects/project_abc123/generate `
  -H "Content-Type: application/json" `
  -d '{
    "scene_count": 3,
    "character_brief": "一位勇敢的女劍士，性格堅毅但內心溫柔"
  }'
```

---

## Step 5: 觀察工作流程

```powershell
# 查看 Orchestrator 日誌
docker-compose logs -f orchestrator

# 查看 Worker 日誌
docker-compose logs -f worker-agent

# 在另一個視窗，檢查作業狀態
curl http://localhost:8000/projects/project_abc123/jobs
```

你應該看到:
1. Orchestrator 建立 `character_analysis` 作業
2. Worker 領取並執行作業
3. 作業完成後，Orchestrator 建立 `story_generation` 作業
4. 依此類推，直到所有階段完成

---

## 🎯 下一步

### 如果你想開發 LLM Worker

1. 閱讀 [LLM_WORKER.md](./LLM_WORKER.md)
2. 取得 OpenAI API Key
3. 複製 `worker-agent` 目錄作為起點
4. 將 mock 函式替換為真實的 LLM API 呼叫

### 如果你想開發 GPU Worker

1. 閱讀 [GPU_WORKER.md](./GPU_WORKER.md)
2. 確認 GPU 硬體需求
3. 建立新的 `worker-gpu` 目錄
4. 實作影像/影片生成邏輯

### 如果你想開發 Orchestrator

1. 閱讀 [ORCHESTRATOR.md](./ORCHESTRATOR.md)
2. 理解狀態機邏輯
3. 在 `apps/orchestrator/main.py` 中實作狀態檢查

---

## 🔧 常見問題

### Worker 無法連線到 API

```powershell
# 檢查 API 是否運行
curl http://localhost:8000/health

# 檢查 Worker 環境變數
docker-compose exec worker-agent env | grep API_BASE_URL
```

### Worker 無法領取作業

```powershell
# 檢查作業佇列
curl http://localhost:8000/projects/project_abc123/jobs

# 檢查 Worker 是否註冊
curl http://localhost:8000/workers
```

### 作業一直處於 queued 狀態

```powershell
# 檢查 Worker 能力是否匹配
docker-compose logs worker-agent | findstr capabilities

# 確認 Worker 的 capabilities 包含作業類型
```

---

## 📊 監控儀表板

### 使用 API 端點監控

```powershell
# 查看所有 Worker
curl http://localhost:8000/workers | python -m json.tool

# 查看專案狀態
curl http://localhost:8000/projects/project_abc123 | python -m json.tool

# 查看作業列表
curl http://localhost:8000/projects/project_abc123/jobs | python -m json.tool
```

### 使用 UI 監控

開啟瀏覽器存取:
- **首頁**: http://localhost:8000/ui
- **專案詳情**: http://localhost:8000/ui/projects/project_abc123

---

## 🧪 完整測試流程

```powershell
# 1. 啟動所有服務
docker-compose up -d

# 2. 等待服務就緒
Start-Sleep -Seconds 10

# 3. 建立測試專案
$project = Invoke-RestMethod -Uri "http://localhost:8000/projects" -Method POST -ContentType "application/json" -Body '{"name":"測試","description":"測試專案","source_prompt":"校園"}'
$projectId = $project.id

# 4. 觸發生成
Invoke-RestMethod -Uri "http://localhost:8000/projects/$projectId/generate" -Method POST -ContentType "application/json" -Body '{"scene_count":3,"character_brief":"女劍士"}'

# 5. 等待完成 (約 1-2 分鐘)
Start-Sleep -Seconds 60

# 6. 檢查最終狀態
Invoke-RestMethod -Uri "http://localhost:8000/projects/$projectId" | Format-List

# 7. 查看作業歷史
Invoke-RestMethod -Uri "http://localhost:8000/projects/$projectId/jobs" | Format-Table
```

---

**版本**: 1.0.0  
**最後更新**: 2026-08-10
