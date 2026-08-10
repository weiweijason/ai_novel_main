# AI 動漫工作室 - Worker 開發文件

## 📋 文件索引

本目錄包含 AI 動漫工作室所有 Worker 的完整開發文件。

| 文件 | 說明 | 適用對象 |
|------|------|---------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | **系統架構總覽** - 整體架構、工作流程、資料模型 | 所有開發者 |
| [WORKER_PROTOCOL.md](./WORKER_PROTOCOL.md) | **Worker 通訊協定** - API 端點、請求/回應格式、錯誤處理 | 所有開發者 |
| [ORCHESTRATOR.md](./ORCHESTRATOR.md) | **Orchestrator 開發指南** - 工作流程協調、狀態機管理、錯誤重試 | 後端開發者 |
| [LLM_WORKER.md](./LLM_WORKER.md) | **LLM Worker 開發指南** - 角色分析、故事生成、腳本生成、場景 JSON | AI/LLM 開發者 |
| [IMAGE_WORKER.md](./IMAGE_WORKER.md) | **Image Worker 開發指南** - ComfyUI 角色/場景圖片生成 | GPU/影像開發者 |
| [VIDEO_WORKER.md](./VIDEO_WORKER.md) | **Video Worker 開發指南** - Wan 場景影片/動畫生成 | GPU/影片開發者 |
| [AUDIO_WORKER.md](./AUDIO_WORKER.md) | **Audio Worker 開發指南** - F5-TTS/Whisper 語音合成 | 音訊開發者 |
| [EDITOR_WORKER.md](./EDITOR_WORKER.md) | **Editor Worker 開發指南** - FFmpeg 最終影片合成 | 影片編輯開發者 |
| [QUICK_START.md](./QUICK_START.md) | **快速開始指南** - 5 分鐘上手測試 | 所有開發者 |
| [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) | **問題排除指南** - 常見錯誤與解決方案 | 所有開發者 |
| [DEPLOYMENT.md](./DEPLOYMENT.md) | **部署指南** - 生產環境配置與擴展 | DevOps 工程師 |

## 🚀 快速開始

### 1. 了解系統架構

首先閱讀 [ARCHITECTURE.md](./ARCHITECTURE.md)，了解：
- 整體系統架構
- Worker 類型與職責
- 工作流程狀態機
- 資料模型結構

### 2. 學習通訊協定

閱讀 [WORKER_PROTOCOL.md](./WORKER_PROTOCOL.md)，了解：
- API 端點規格
- 請求/回應格式
- 錯誤處理機制
- 測試方法

### 3. 選擇你要開發的 Worker

| 如果你想... | 閱讀這個文件 |
|------------|-------------|
| 實作工作流程協調邏輯 | [ORCHESTRATOR.md](./ORCHESTRATOR.md) |
| 整合 LLM API (OpenAI/Claude) | [LLM_WORKER.md](./LLM_WORKER.md) |
| 實作 ComfyUI 圖片生成 (RTX 5090) | [IMAGE_WORKER.md](./IMAGE_WORKER.md) |
| 實作 Wan 影片生成 (RTX 5080) | [VIDEO_WORKER.md](./VIDEO_WORKER.md) |
| 實作 F5-TTS 語音合成 (RTX 5060 Ti) | [AUDIO_WORKER.md](./AUDIO_WORKER.md) |
| 實作 FFmpeg 影片合成 | [EDITOR_WORKER.md](./EDITOR_WORKER.md) |
| 快速上手測試 | [QUICK_START.md](./QUICK_START.md) |
| 排除常見問題 | [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) |
| 部署到生產環境 | [DEPLOYMENT.md](./DEPLOYMENT.md) |

## 📊 工作流程圖

```
使用者建立專案
    │
    ▼
┌─────────────────────────────────────────────┐
│              API 服務層                       │
│  • 專案管理                                   │
│  • Worker 註冊/心跳                           │
│  • 作業佇列管理                                │
│  • 圖片上傳 (MinIO)                           │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│           Orchestrator                       │
│  • 監控專案狀態                               │
│  • 排程新作業                                 │
│  • 處理錯誤重試                               │
└──────────────────┬──────────────────────────┘
                   │
          ┌────────┴────────┐
          ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AI Worker 執行層                              │
│                                                                  │
│  ┌──────────────┐                                               │
│  │  LLM Worker  │  (文字生成)                                    │
│  │  RTX 5090    │  • 角色分析                                     │
│  │  24GB        │  • 故事生成                                     │
│  └──────┬───────┘  • 腳本生成                                     │
│         │             • 場景 JSON                                 │
│         ▼                                                        │
│  ┌──────────────┐                                               │
│  │ Image Worker │  (圖片生成)                                    │
│  │  RTX 5090    │  • 角色立繪 (ComfyUI)                          │
│  │  32GB        │  • 場景圖片                                     │
│  └──────┬───────┘  • 背景圖片                                     │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────┐                                               │
│  │ Video Worker │  (影片生成)                                    │
│  │  RTX 5080    │  • 場景影片 (Wan)                              │
│  │  16GB        │  • 角色動畫                                     │
│  └──────┬───────┘  • 鏡頭運動                                     │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────┐                                               │
│  │ Audio Worker │  (音訊生成)                                    │
│  │  RTX 5060 Ti │  • 語音合成 (F5-TTS)                           │
│  │  8GB         │  • 語音辨識 (Whisper)                          │
│  └──────┬───────┘  • 背景音樂                                     │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────┐                                               │
│  │Editor Worker │  (最終合成)                                    │
│  │  CPU + GPU   │  • 影片合成 (FFmpeg)                           │
│  │  (可選)      │  • 音訊同步                                     │
│  └──────┬───────┘  • 字幕嵌入                                     │
│         │             • 最終 MP4                                  │
│         ▼                                                        │
│  ┌──────────────┐                                               │
│  │  Final MP4   │                                                │
│  └──────────────┘                                               │
└─────────────────────────────────────────────────────────────────┘
```

## 🔧 環境設定

### 必要工具

- **Python 3.11+**
- **Docker & Docker Compose**
- **PostgreSQL 16** (Docker 容器)
- **Redis 7** (Docker 容器)
- **MinIO** (Docker 容器)

### 可選工具

- **NVIDIA GPU** (GPU Worker)
- **CUDA 12.1+** (GPU Worker)
- **OpenAI API Key** (LLM Worker)
- **Anthropic API Key** (LLM Worker)

### 啟動開發環境

```bash
# 1. 複製環境變數範本
cp .env.example .env

# 2. 編輯環境變數
# 設定 POSTGRES_PASSWORD, MINIO_ACCESS_KEY, MINIO_SECRET_KEY

# 3. 啟動基礎服務
docker-compose up -d postgres redis minio

# 4. 啟動 API 服務
docker-compose up -d api

# 5. 啟動 Orchestrator
docker-compose up -d orchestrator

# 6. 啟動 Worker (根據你要開發的 Worker)
docker-compose up -d worker-agent
```

## 📝 開發檢查清單

### LLM Worker 開發者

- [ ] 閱讀 [LLM_WORKER.md](./LLM_WORKER.md)
- [ ] 設定 OpenAI/Claude API Key
- [ ] 實作 `register_worker()`
- [ ] 實作 `claim_job()`
- [ ] 實作 `run_llm_job()` 針對每個作業類型
- [ ] 實作 `update_job_status()`
- [ ] 實作 `send_heartbeat()`
- [ ] 測試所有 4 種作業類型
- [ ] 實作錯誤處理與重試

### GPU Worker 開發者

- [ ] 閱讀 [GPU_WORKER.md](./GPU_WORKER.md)
- [ ] 設定 NVIDIA GPU 與 CUDA
- [ ] 安裝 PyTorch 與 Diffusers
- [ ] 實作 GPU 資源管理
- [ ] 實作 `register_worker()`
- [ ] 實作 `claim_job()`
- [ ] 實作影像生成函式
- [ ] 實作影片生成函式
- [ ] 實作 MinIO 上傳
- [ ] 測試 VRAM 最佳化
- [ ] 實作錯誤處理與重試

### Orchestrator 開發者

- [ ] 閱讀 [ORCHESTRATOR.md](./ORCHESTRATOR.md)
- [ ] 理解專案狀態機
- [ ] 實作 `check_project_state()`
- [ ] 實作 `process_failed_jobs()`
- [ ] 實作 `enqueue_llm_job()`
- [ ] 測試完整工作流程
- [ ] 測試錯誤重試機制
- [ ] 實作監控與警報

## 🧪 測試流程

### 1. 單元測試

```bash
# 測試 Worker 註冊
pytest tests/test_worker_register.py

# 測試作業領取
pytest tests/test_job_claim.py

# 測試 LLM 任務
pytest tests/test_llm_tasks.py
```

### 2. 整合測試

```bash
# 啟動測試環境
docker-compose -f docker-compose.test.yml up -d

# 執行整合測試
pytest tests/integration/

# 清理測試環境
docker-compose -f docker-compose.test.yml down
```

### 3. 手動測試

```bash
# 1. 建立專案
curl -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "測試專案",
    "description": "測試描述",
    "source_prompt": "校園生活"
  }'

# 2. 觸發生成
curl -X POST http://localhost:8000/projects/project_123/generate \
  -H "Content-Type: application/json" \
  -d '{
    "scene_count": 5,
    "character_brief": "一位勇敢的女劍士"
  }'

# 3. 觀察 Orchestrator 日誌
docker-compose logs -f orchestrator

# 4. 觀察 Worker 日誌
docker-compose logs -f worker-agent

# 5. 檢查作業狀態
curl http://localhost:8000/projects/project_123/jobs
```

## 📚 額外資源

- [FastAPI 官方文件](https://fastapi.tiangolo.com/)
- [SQLAlchemy 官方文件](https://docs.sqlalchemy.org/)
- [OpenAI API 文件](https://platform.openai.com/docs/)
- [Diffusers 文件](https://huggingface.co/docs/diffusers/)
- [MinIO Python SDK](https://min.io/docs/minio/linux/developers/python/API-reference.html#list-buckets)

## 🤝 貢獻指南

1. Fork 專案
2. 建立功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交變更 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 建立 Pull Request

## 📄 授權

本專案採用 MIT 授權。詳情請參閱 [LICENSE](../../LICENSE) 文件。

---

**版本**: 1.0.0  
**最後更新**: 2026-08-10  
**維護者**: AI 動漫工作室團隊
