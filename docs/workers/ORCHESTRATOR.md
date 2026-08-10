# Orchestrator 工作流程協調器 - 開發指南

## 📋 概述

Orchestrator 是 AI 動漫工作室的核心協調器，負責管理專案的完整工作流程，確保每個階段按順序執行，處理錯誤重試，並維護專案狀態的一致性。

## 🎯 職責

- **狀態機管理**: 追蹤每個專案的當前階段
- **依賴檢查**: 確保前置作業完成才啟動後續作業
- **錯誤處理**: 監控失敗的作業並執行重試策略
- **狀態同步**: 更新 Project、Episode、Scene 的狀態

## 🏗️ 系統架構

```
┌──────────────────────────────────────────────────────┐
│                  Orchestrator Loop                    │
│                                                       │
│  ┌─────────────────────────────────────────────────┐  │
│  │  1. 清理逾時作業 (Timeout Cleanup)               │  │
│  │  2. 處理失敗作業 (Retry Failed Jobs)             │  │
│  │  3. 檢查專案狀態 (Project State Machine)         │  │
│  │  4. 排程新作業 (Enqueue Pending Jobs)            │  │
│  └─────────────────────────────────────────────────┘  │
│                                                       │
│  輪詢間隔: ORCHESTRATOR_POLL_SECONDS (預設 3s)         │
└──────────────────────────────────────────────────────┘
```

## 🔄 工作流程狀態機

### 專案狀態轉換圖

```
draft
  │
  ├─[使用者觸發 generate]─► character_analysis_pending
  │                            │
  │                        [完成]
  │                            ▼
  │                     story_generation_pending
  │                            │
  │                        [完成]
  │                            ▼
  │                     script_generation_pending
  │                            │
  │                        [完成]
  │                            ▼
  │                     scene_json_pending
  │                            │
  │                        [完成]
  │                            ▼
  │                     ready_for_gpu
  │
  └────────────────────────────┘
           │
      [任何階段失敗]
           ▼
        failed
```

## 📊 資料模型

### Project 狀態欄位

```python
class Project:
    id: str                          # 專案 ID
    name: str                        # 專案名稱
    status: str                      # 當前狀態
    workflow_data: dict              # 工作流程參數
    character_profile: dict | None   # 角色分析結果
    story_data: dict | None          # 故事生成結果
    script_data: dict | None         # 腳本生成結果
```

### Job 結構

```python
class Job:
    id: str
    project_id: str
    episode_id: str | None
    scene_id: str | None
    job_type: str                    # 作業類型
    status: str                      # queued/running/completed/failed
    priority: int                    # 優先級 (1-10, 1 最高)
    attempt: int                     # 當前嘗試次數
    max_attempts: int                # 最大重試次數
    payload: dict                    # 輸入參數
    result: dict | None              # 輸出結果
    error: str | None                # 錯誤訊息
```

## 🔧 環境變數

| 變數名稱 | 說明 | 預設值 |
|---------|------|--------|
| `DATABASE_URL` | PostgreSQL 連線字串 | `sqlite:///./anime.db` |
| `ORCHESTRATOR_POLL_SECONDS` | 輪詢間隔 (秒) | `3` |
| `MAX_JOB_ATTEMPTS` | 作業最大重試次數 | `3` |
| `JOB_TIMEOUT_SECONDS` | 作業逾時時間 (秒) | `3600` |

## 📝 核心函式說明

### `process_failed_jobs(db)`
清理並重試失敗的作業

```python
def process_failed_jobs(db):
    """
    1. 找出 status='failed' 的作業
    2. 檢查 attempt < max_attempts
    3. 如果可重試，重置為 'queued'
    4. 如果超過重試次數，更新 project status='failed'
    """
```

### `check_project_state(db, project)`
檢查專案狀態並排程下一個作業

```python
def check_project_state(db, project):
    """
    狀態檢查邏輯:
    - character_analysis_pending: 檢查 character_analysis 作業是否完成
    - story_generation_pending: 檢查 story_generation 作業是否完成
    - script_generation_pending: 檢查 script_generation 作業是否完成
    - scene_json_pending: 檢查所有 scene_json_generation 作業是否完成
    """
```

### `enqueue_llm_job(db, ...)`
建立新的 LLM 作業

```python
def enqueue_llm_job(
    db,
    *,
    project_id: str,
    episode_id: str | None,
    scene_id: str | None,
    job_type: str,
    payload: dict
) -> None:
    """
    建立 Job 記錄:
    - worker_type='llm'
    - status='queued'
    - priority=2
    - attempt=0
    - max_attempts=3
    """
```

## 🚀 開發步驟

### 1. 設定開發環境

```bash
# 建立虛擬環境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate     # Windows

# 安裝依賴
pip install -r requirements.txt
```

### 2. 實作狀態機邏輯

```python
# 在 main.py 中實作 check_project_state

def check_project_state(db, project):
    """檢查專案狀態並排程下一個作業"""
    
    # 階段 1: 角色分析完成 → 啟動故事生成
    if project.status == "character_analysis_pending":
        char_job = latest_completed_job(db, project.id, "character_analysis")
        if char_job and char_job.status == "completed":
            # 儲存角色資料
            project.character_profile = char_job.result
            project.status = "story_generation_pending"
            db.commit()
            
            # 排程故事生成作業
            enqueue_llm_job(
                db,
                project_id=project.id,
                episode_id=project.workflow_data.get("episode_id"),
                scene_id=None,
                job_type="story_generation",
                payload={
                    "topic": project.source_prompt or "",
                    "character_profile": project.character_profile
                }
            )
    
    # 階段 2: 故事生成完成 → 啟動腳本生成
    elif project.status == "story_generation_pending":
        story_job = latest_completed_job(db, project.id, "story_generation")
        if story_job and story_job.status == "completed":
            project.story_data = story_job.result
            project.status = "script_generation_pending"
            db.commit()
            
            enqueue_llm_job(
                db,
                project_id=project.id,
                episode_id=project.workflow_data.get("episode_id"),
                scene_id=None,
                job_type="script_generation",
                payload={
                    "title": project.story_data.get("title"),
                    "story_data": project.story_data
                }
            )
    
    # 階段 3: 腳本生成完成 → 啟動場景 JSON 生成
    elif project.status == "script_generation_pending":
        script_job = latest_completed_job(db, project.id, "script_generation")
        if script_job and script_job.status == "completed":
            project.script_data = script_job.result
            project.status = "scene_json_pending"
            db.commit()
            
            # 為每個場景建立作業
            scenes = db.scalars(
                select(Scene).where(Scene.episode_id == project.workflow_data["episode_id"])
            ).all()
            
            for scene in scenes:
                if not has_scene_job(db, project.id, scene.id, "scene_json_generation"):
                    enqueue_llm_job(
                        db,
                        project_id=project.id,
                        episode_id=project.workflow_data["episode_id"],
                        scene_id=scene.id,
                        job_type="scene_json_generation",
                        payload={
                            "scene_id": scene.id,
                            "scene_number": scene.scene_number,
                            "script_data": project.script_data
                        }
                    )
    
    # 階段 4: 所有場景完成 → 專案就緒
    elif project.status == "scene_json_pending":
        scenes = db.scalars(
            select(Scene).where(Scene.episode_id == project.workflow_data["episode_id"])
        ).all()
        
        all_completed = all(
            scene.status == "scene_json_ready"
            for scene in scenes
        )
        
        if all_completed:
            project.status = "ready_for_gpu"
            db.commit()
```

### 3. 實作錯誤重試邏輯

```python
def process_failed_jobs(db):
    """處理失敗的作業"""
    failed_jobs = db.scalars(
        select(Job).where(
            Job.status == "failed",
            Job.attempt < Job.max_attempts
        )
    ).all()
    
    for job in failed_jobs:
        # 重試: 重置為 queued
        job.status = "queued"
        job.attempt += 1
        job.worker_id = None
        
        # 如果超過重試次數，標記專案為失敗
        if job.attempt >= job.max_attempts:
            project = db.get(Project, job.project_id)
            if project:
                project.status = "failed"
    
    db.commit()
```

### 4. 測試

```bash
# 啟動 orchestrator
DATABASE_URL=postgresql+psycopg://anime:anime@localhost:5432/anime \
python main.py

# 觀察日誌輸出
# 應該看到每 3 秒檢查一次專案狀態
```

## 🧪 測試清單

- [ ] 新專案建立後狀態為 `draft`
- [ ] 觸發 generate 後狀態變為 `character_analysis_pending`
- [ ] 角色分析完成後自動啟動故事生成
- [ ] 故事生成完成後自動啟動腳本生成
- [ ] 腳本生成完成後為每個場景建立作業
- [ ] 所有場景完成後狀態變為 `ready_for_gpu`
- [ ] 作業失敗後自動重試 (最多 3 次)
- [ ] 超過重試次數後專案狀態變為 `failed`
- [ ] 逾時作業被正確清理

## 🔍 除錯技巧

### 查看當前專案狀態
```sql
SELECT id, name, status, character_profile, story_data, script_data
FROM projects
ORDER BY created_at DESC;
```

### 查看作業佇列
```sql
SELECT j.id, j.job_type, j.status, j.attempt, j.payload
FROM jobs j
WHERE j.project_id = 'project_123'
ORDER BY j.created_at DESC;
```

### 檢查 Worker 狀態
```sql
SELECT id, worker_type, status, last_heartbeat, current_job
FROM workers;
```

## 📚 相關文件

- [Worker 架構總覽](./ARCHITECTURE.md)
- [LLM Worker 開發指南](./LLM_WORKER.md)
- [Worker 通訊協定](./WORKER_PROTOCOL.md)

---

**版本**: 1.0.0  
**最後更新**: 2026-08-10
