# AI 動漫工作室 - Worker 架構總覽

## 📋 目錄
- [系統架構](#系統架構)
- [Worker 類型](#worker-類型)
- [工作流程](#工作流程)
- [通訊協定](#通訊協定)
- [資料模型](#資料模型)
- [開發指南索引](#開發指南索引)

---

## 系統架構

```
┌─────────────────────────────────────────────────────────────┐
│                        使用者介面 (UI)                        │
│                     FastAPI + Jinja2                        │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      API 服務層                              │
│  ┌─────────────┐  ┌─────────────┐  ┌────────────────────┐  │
│  │ 專案管理     │  │ Worker 註冊  │  │  圖片上傳 (MinIO)  │  │
│  │ 作業排程     │  │ 心跳監控     │  │  資產管理          │  │
│  └─────────────┘  └─────────────┘  └────────────────────┘  │
│                           │                                  │
│                    PostgreSQL 16                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
                    ┌──────┴──────┐
                    ▼             ▼
┌─────────────────────────┐  ┌─────────────────────────┐
│   Orchestrator          │  │   Worker Agent          │
│   (工作流程協調器)        │  │   (作業代理)             │
│                         │  │                         │
│  • 狀態機管理            │◄─┤  • 作業領取              │
│  • 依賴檢查              │  │  • 作業執行              │
│  • 錯誤重試              │  │  • 狀態回報              │
└─────────────────────────┘  └─────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    AI Worker 執行層                          │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌────────────────────┐  │
│  │  LLM Worker │  │Image Worker │  │  Video Worker      │  │
│  │  (文字生成)  │  │  (圖片生成)  │  │  (影片生成)        │  │
│  │  RTX 5090   │  │  RTX 5090   │  │  RTX 5080          │  │
│  │  24GB       │  │  32GB       │  │  16GB              │  │
│  └─────────────┘  └─────────────┘  └────────────────────┘  │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐                          │
│  │Audio Worker │  │Editor Worker│                          │
│  │  (音訊生成)  │  │  (最終合成)  │                          │
│  │  RTX 5060 Ti│  │  CPU + GPU  │                          │
│  │  8GB        │  │  (可選)     │                          │
│  └─────────────┘  └─────────────┘                          │
└─────────────────────────────────────────────────────────────┘
```

## Worker 類型

| Worker 類型 | 用途 | 優先級 | 硬體需求 | 依賴資源 |
|------------|------|--------|---------|----------|
| `llm` | 文字生成（角色、故事、腳本、場景） | 高 | RTX 5090 24GB | CPU, OpenAI API Key |
| `image` | 圖片生成（角色、場景、背景） | 高 | RTX 5090 32GB | ComfyUI, Stable Diffusion |
| `video` | 影片生成（場景、動畫、鏡頭） | 中 | RTX 5080 16GB | Wan, ControlNet |
| `audio` | 音訊生成（語音、BGM、音效） | 中 | RTX 5060 Ti 8GB | F5-TTS, Whisper |
| `editor` | 最終合成（影片、音訊、字幕） | 低 | CPU + GPU (可選) | FFmpeg |

## 工作流程

### 完整製作流程

```
使用者建立專案
    │
    ▼
🎭 角色分析 (character_analysis)
    │  - 分析角色描述
    │  - 生成性格/外觀設定
    │  - 配置語音參數
    │
    ▼
📖 故事生成 (story_generation)
    │  - 生成劇本大綱
    │  - 建立集數結構
    │  - 撰寫劇情摘要
    │
    ▼
📝 腳本生成 (script_generation)
    │  - 分場腳本
    │  - 對話內容
    │  - 場景描述
    │
    ▼
🎬 場景 JSON 生成 (scene_json_generation)
    │  - 場景結構化資料
    │  - 鏡頭設定
    │  - 視覺提示詞
    │  - 音效配置
    │
    ▼
🎨 角色圖片生成 (character_image)
    │  - 角色立繪 (ComfyUI)
    │  - 表情變化
    │  - 姿勢變化
    │
    ▼
🖼️ 場景圖片生成 (scene_image)
    │  - 場景背景
    │  - 角色置入
    │  - 光影效果
    │
    ▼
🎥 場景影片生成 (scene_video)
    │  - 場景動畫 (Wan)
    │  - 角色動作
    │  - 鏡頭運動
    │
    ▼
🎤 語音合成 (voice_synthesis)
    │  - 角色對話 (F5-TTS)
    │  - 語音克隆
    │  - 情緒控制
    │
    ▼
🎵 背景音樂生成 (bgm_generation)
    │  - 情緒音樂
    │  - 類型配樂
    │  - 長度調整
    │
    ▼
🎞️ 最終影片合成 (video_composition)
    │  - 影片 + 音訊混合 (FFmpeg)
    │  - 字幕嵌入
    │  - 音訊同步
    │
    ▼
🎬 最終渲染 (final_render)
    │  - 整集串接
    │  - 場景轉換
    │  - 片尾字幕
    │
    ▼
✅ 完成 (completed)
    │  - 最終 MP4
    │  - 上傳 MinIO
    │  - 通知使用者
    │  - BGM 生成
    │  - 語音合成
    │  - 音效混合
    │
    ▼
✅ 專案就緒 (ready_for_gpu)
```

## 通訊協定

### Worker 註冊
```http
POST /worker/register
Content-Type: application/json

{
  "worker_id": "llm-01",
  "worker_type": "llm",
  "hostname": "worker-hostname",
  "capabilities": ["character_analysis", "story_generation"],
  "models": ["gpt-4", "claude-3"]
}
```

### 心跳回報
```http
POST /worker/heartbeat
Content-Type: application/json

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

### 領取作業
```http
POST /worker/jobs/claim
Content-Type: application/json

{
  "worker_id": "llm-01"
}
```

### 更新作業狀態
```http
POST /worker/jobs/{job_id}/status
Content-Type: application/json

{
  "status": "running|completed|failed",
  "progress": 0.75,
  "result": { ... },
  "error": "錯誤訊息 (如果失敗)"
}
```

## 資料模型

### Job 狀態機
```
queued → running → completed
              │
              └──→ failed → queued (重試)
```

### 作業類型對應表

| job_type | 輸入 payload | 輸出 result | 儲存欄位 |
|----------|-------------|------------|---------|
| character_analysis | brief, project_name | name, personality, appearance | project.character_profile |
| story_generation | topic, character_profile | title, synopsis | project.story_data |
| script_generation | title, story_data | scenes[] | project.script_data |
| scene_json_generation | scene_id, line | scene_json | scene.scene_data |

## 開發指南索引

| 文件 | 說明 | 適用對象 |
|------|------|---------|
| [ORCHESTRATOR.md](./ORCHESTRATOR.md) | 工作流程協調器開發指南 | 後端開發者 |
| [LLM_WORKER.md](./LLM_WORKER.md) | LLM Worker 開發指南 | AI/LLM 開發者 |
| [GPU_WORKER.md](./GPU_WORKER.md) | GPU Worker 開發指南 | GPU/影像開發者 |
| [WORKER_PROTOCOL.md](./WORKER_PROTOCOL.md) | Worker 通訊協定詳細說明 | 所有開發者 |

---

**版本**: 1.0.0  
**最後更新**: 2026-08-10
