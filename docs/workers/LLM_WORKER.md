# LLM Worker - 開發指南

## 📋 概述

LLM Worker 負責所有文字生成任務，包括角色分析、故事生成、腳本生成和場景 JSON 生成。這是 AI 動漫工作室的核心 AI 引擎。

## 🎯 職責

| 作業類型 | 說明 | 輸入 | 輸出 |
|---------|------|------|------|
| `character_analysis` | 分析角色描述，生成完整角色設定 | brief, project_name | name, personality, appearance, voice_config |
| `story_generation` | 根據主題生成故事大綱 | topic, character_profile | title, synopsis, plot_points |
| `script_generation` | 生成分場腳本與對話 | title, story_data | scenes[], dialogues |
| `scene_json_generation` | 生成結構化場景 JSON | scene_id, script_data | scene_json (完整場景結構) |

## 🏗️ 系統架構

```
┌─────────────────────────────────────────────────────┐
│                  LLM Worker Loop                     │
│                                                      │
│  ┌──────────┐    ┌──────────┐    ┌──────────────┐   │
│  │ 1. Register│──►│ 2. Claim  │──►│ 3. Execute   │   │
│  │  (註冊)    │    │  (領取)   │    │  (執行)      │   │
│  └──────────┘    └──────────┘    └──────┬───────┘   │
│                                         │            │
│  ┌──────────┐    ┌──────────┐    ┌──────▼───────┐   │
│  │ 5. Heartbeat│◄─│ 4. Update │◄─│ 4. Update    │   │
│  │  (心跳)    │    │  (回報)   │    │  (狀態回報)  │   │
│  └──────────┘    └──────────┘    └──────────────┘   │
│                                                      │
│  輪詢間隔: POLL_INTERVAL_SECONDS (預設 3s)            │
└─────────────────────────────────────────────────────┘
```

## 🔧 環境變數

| 變數名稱 | 說明 | 預設值 |
|---------|------|--------|
| `API_BASE_URL` | API 服務位址 | `http://localhost:8000` |
| `WORKER_ID` | Worker 唯一識別碼 | `llm-01` |
| `WORKER_TYPE` | Worker 類型 | `llm` |
| `WORKER_HOSTNAME` | Worker 主機名稱 | `llm-worker` |
| `WORKER_CAPABILITIES` | 支援的作業類型 (逗號分隔) | `character_analysis,story_generation,script_generation,scene_json_generation` |
| `POLL_INTERVAL_SECONDS` | 輪詢間隔 (秒) | `3` |
| `OPENAI_API_KEY` | OpenAI API 金鑰 | (必填) |
| `LLM_MODEL` | 使用的 LLM 模型 | `gpt-4o` |
| `LLM_MAX_TOKENS` | 最大 token 數 | `4096` |
| `LLM_TEMPERATURE` | 生成溫度 (0-2) | `0.7` |

## 📝 核心函式說明

### 1. Worker 註冊

```python
def register_worker() -> None:
    """
    向 API 註冊 Worker
    
    Request:
    POST /worker/register
    {
        "worker_id": "llm-01",
        "worker_type": "llm",
        "hostname": "llm-worker",
        "capabilities": ["character_analysis", "story_generation", ...],
        "models": ["gpt-4o"]
    }
    
    Response: 200 OK
    """
```

### 2. 領取作業

```python
def claim_job() -> dict | None:
    """
    從佇列領取下一個作業
    
    Request:
    POST /worker/jobs/claim
    {
        "worker_id": "llm-01"
    }
    
    Response:
    - 200: 作業資料
    - 404: 沒有可用作業
    """
```

### 3. 執行作業

```python
def run_llm_job(job: dict) -> dict:
    """
    根據 job_type 執行對應的 LLM 任務
    
    Args:
        job: {
            "id": "job_123",
            "type": "character_analysis",
            "input": { ... }
        }
    
    Returns:
        {
            "result": { ... },  # 作業結果
            "progress": 1.0     # 完成進度
        }
    """
```

### 4. 更新作業狀態

```python
def update_job_status(
    job_id: str,
    status: str,        # running | completed | failed
    progress: float,    # 0.0 - 1.0
    result: dict,       # 作業結果
    error: str          # 錯誤訊息
) -> None:
    """
    回報作業狀態給 API
    
    Request:
    POST /worker/jobs/{job_id}/status
    {
        "status": "running",
        "progress": 0.5,
        "result": { ... },
        "error": "error message"
    }
    """
```

### 5. 心跳回報

```python
def send_heartbeat(status: str, current_job: str | None) -> None:
    """
    定期回報 Worker 狀態
    
    Request:
    POST /worker/heartbeat
    {
        "worker_id": "llm-01",
        "status": "busy",
        "current_job": "job_123",
        "gpu": { ... }
    }
    """
```

## 🤖 LLM 任務實作

### 1. 角色分析 (character_analysis)

```python
def _character_analysis(user_input: dict) -> dict:
    """
    分析角色描述，生成完整角色設定
    
    Input:
    {
        "brief": "一位勇敢的女劍士，性格堅毅但內心溫柔",
        "project_name": "我的動漫故事"
    }
    
    Output:
    {
        "name": "艾莉亞",
        "summary": "一位勇敢的女劍士...",
        "personality": {
            "traits": ["勇敢", "堅毅", "溫柔", "負責任"],
            "strengths": ["戰鬥技巧", "領導力"],
            "weaknesses": ["不善表達情感"],
            "fears": ["失去重要的人"]
        },
        "appearance": {
            "style": "anime",
            "hair": "長銀髮",
            "eyes": "藍色",
            "clothing": "輕甲鎧",
            "accessories": ["佩劍", "護腕"]
        },
        "voice_config": {
            "pitch": "medium",
            "tone": "determined",
            "speed": "normal"
        }
    }
    """
    
    prompt = f"""
    請根據以下描述，為動漫專案「{user_input['project_name']}」生成一個完整的角色設定。
    
    角色描述: {user_input['brief']}
    
    請以 JSON 格式回覆，包含以下欄位:
    - name: 角色名稱 (日文風格)
    - summary: 角色簡介 (50字以內)
    - personality: 性格特質 (traits, strengths, weaknesses, fears)
    - appearance: 外觀設定 (style, hair, eyes, clothing, accessories)
    - voice_config: 語音配置 (pitch, tone, speed)
    
    確保角色設定符合動漫風格，具有獨特性和吸引力。
    """
    
    response = call_llm(prompt, max_tokens=1024)
    return parse_json_response(response)
```

### 2. 故事生成 (story_generation)

```python
def _story_generation(user_input: dict) -> dict:
    """
    根據主題和角色設定生成故事大綱
    
    Input:
    {
        "topic": "校園生活",
        "character_profile": { ... }
    }
    
    Output:
    {
        "title": "青春旋律 - 第一集",
        "synopsis": "在櫻花飄落的季節...",
        "plot_points": [
            {
                "act": 1,
                "description": "開場：主角轉學到新學校",
                "key_events": ["介紹主角", "遇見新朋友", "發現秘密"]
            },
            {
                "act": 2,
                "description": "發展：文化祭準備",
                "key_events": ["團隊合作", "衝突產生", "情感昇華"]
            },
            {
                "act": 3,
                "description": "高潮：文化祭當天",
                "key_events": ["危機出現", "主角成長", "感人結局"]
            }
        ],
        "themes": ["友情", "成長", "青春"],
        "tone": "溫馨、勵志"
    }
    """
    
    prompt = f"""
    請為動漫專案生成一個完整的故事大綱。
    
    主題: {user_input['topic']}
    主要角色: {json.dumps(user_input.get('character_profile', {}), ensure_ascii=False)}
    
    請以 JSON 格式回覆，包含:
    - title: 故事標題
    - synopsis: 故事摘要 (100字以內)
    - plot_points: 劇情要點 (3 個 act，每個包含 description 和 key_events)
    - themes: 故事主題 (3-5 個)
    - tone: 故事基調
    
    確保故事結構完整，符合動漫敘事風格。
    """
    
    response = call_llm(prompt, max_tokens=2048)
    return parse_json_response(response)
```

### 3. 腳本生成 (script_generation)

```python
def _script_generation(user_input: dict) -> dict:
    """
    生成分場腳本與對話
    
    Input:
    {
        "title": "青春旋律 - 第一集",
        "story_data": { ... }
    }
    
    Output:
    {
        "title": "青春旋律 - 第一集",
        "scenes": [
            {
                "scene_number": 1,
                "location": "學校大門口",
                "time": "清晨",
                "description": "主角帶著行李來到新學校",
                "dialogues": [
                    {
                        "character": "主角",
                        "line": "這就是我即將就讀的學校嗎？",
                        "emotion": "期待"
                    },
                    {
                        "character": "旁白",
                        "line": "新的人生，即將開始...",
                        "emotion": "平靜"
                    }
                ]
            },
            ...
        ]
    }
    """
    
    prompt = f"""
    請根據以下故事大綱，生成詳細的分場腳本。
    
    標題: {user_input['title']}
    故事大綱: {json.dumps(user_input['story_data'], ensure_ascii=False)}
    
    請以 JSON 格式回覆，包含:
    - title: 腳本標題
    - scenes: 場景列表，每個場景包含:
        - scene_number: 場景編號
        - location: 場景地點
        - time: 時間
        - description: 場景描述
        - dialogues: 對話列表 (character, line, emotion)
    
    生成 5-8 個場景，確保:
    1. 對話自然流暢
    2. 情感表達豐富
    3. 符合動漫風格
    4. 每個場景有明確的目的
    """
    
    response = call_llm(prompt, max_tokens=4096)
    return parse_json_response(response)
```

### 4. 場景 JSON 生成 (scene_json_generation)

```python
def _scene_json_generation(user_input: dict) -> dict:
    """
    生成結構化場景 JSON (供 GPU Worker 使用)
    
    Input:
    {
        "scene_id": "scene_001",
        "scene_number": 1,
        "script_data": { ... }
    }
    
    Output:
    {
        "schema_version": "1.0",
        "scene_id": "scene_001",
        "duration": 6,
        "location": {
            "id": "school_gate",
            "description": "學校大門口",
            "time": "morning",
            "weather": "clear"
        },
        "characters": [
            {
                "character_id": "char_001",
                "name": "主角",
                "position": {"x": 0.5, "y": 0.7},
                "expression": "happy",
                "pose": "standing"
            }
        ],
        "camera": {
            "shot": "medium",
            "angle": "eye_level",
            "movement": "static"
        },
        "dialogues": [
            {
                "sequence": 1,
                "character_id": "char_001",
                "text": "這就是我即將就讀的學校嗎？",
                "emotion": "期待",
                "duration": 3.0
            }
        ],
        "visual": {
            "style": "anime",
            "prompt": "anime style, school gate, morning light, cherry blossoms",
            "negative_prompt": "blurry, low quality, distorted"
        },
        "video": {
            "prompt": "subtle cherry blossom petals falling",
            "motion_strength": 0.3,
            "camera_motion": "static"
        },
        "audio": {
            "bgm": "light_piano",
            "ambient": ["bird_chirping", "wind"],
            "sfx": []
        }
    }
    """
    
    prompt = f"""
    請將以下腳本場景轉換為結構化的場景 JSON，供 GPU 渲染使用。
    
    場景 ID: {user_input['scene_id']}
    場景編號: {user_input['scene_number']}
    腳本資料: {json.dumps(user_input['script_data'], ensure_ascii=False)}
    
    請以 JSON 格式回覆，包含:
    - schema_version: "1.0"
    - scene_id: 場景 ID
    - duration: 場景持續時間 (秒)
    - location: 地點設定 (id, description, time, weather)
    - characters: 角色列表 (character_id, name, position, expression, pose)
    - camera: 鏡頭設定 (shot, angle, movement)
    - dialogues: 對話列表 (sequence, character_id, text, emotion, duration)
    - visual: 視覺設定 (style, prompt, negative_prompt)
    - video: 影片設定 (prompt, motion_strength, camera_motion)
    - audio: 音效設定 (bgm, ambient, sfx)
    
    確保:
    1. visual.prompt 包含詳細的動漫風格描述
    2. camera 設定符合場景氛圍
    3. audio 設定與場景情緒匹配
    4. 所有欄位符合 schema 規範
    """
    
    response = call_llm(prompt, max_tokens=2048)
    return parse_json_response(response)
```

## 🔌 LLM API 整合

### OpenAI API 整合範例

```python
import openai

def call_llm(prompt: str, max_tokens: int = 4096) -> str:
    """
    呼叫 LLM API
    
    Args:
        prompt: 提示詞
        max_tokens: 最大 token 數
    
    Returns:
        LLM 回應文字
    """
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL", "gpt-4o"),
        messages=[
            {"role": "system", "content": "你是一個專業的動漫腳本撰寫助手。請以 JSON 格式回覆。"},
            {"role": "user", "content": prompt}
        ],
        max_tokens=max_tokens,
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
        response_format={"type": "json_object"}
    )
    
    return response.choices[0].message.content
```

### Claude API 整合範例

```python
import anthropic

def call_llm_claude(prompt: str, max_tokens: int = 4096) -> str:
    """
    呼叫 Claude API
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    message = client.messages.create(
        model=os.getenv("LLM_MODEL", "claude-3-opus-20240229"),
        max_tokens=max_tokens,
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
        system="你是一個專業的動漫腳本撰寫助手。請以 JSON 格式回覆。",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    return message.content[0].text
```

## 🚀 開發步驟

### 1. 設定環境

```bash
# 建立虛擬環境
python -m venv venv
source venv/bin/activate

# 安裝依賴
pip install openai anthropic requests

# 設定環境變數
export OPENAI_API_KEY="your-api-key"
export LLM_MODEL="gpt-4o"
```

### 2. 實作 Worker 主迴圈

```python
import time
import sys

def main():
    # 註冊 Worker
    register_worker()
    send_heartbeat("idle", None)
    
    current_job = None
    
    while True:
        try:
            if current_job is None:
                # 嘗試領取作業
                job = claim_job()
                if job:
                    current_job = job
                    send_heartbeat("busy", job["id"])
                    
                    # 開始執行
                    update_job_status(job["id"], "running", progress=0.0)
            
            if current_job:
                # 執行作業
                result = run_llm_job(current_job)
                
                # 回報完成
                update_job_status(
                    current_job["id"],
                    "completed",
                    progress=1.0,
                    result=result
                )
                
                current_job = None
                send_heartbeat("idle", None)
            else:
                time.sleep(POLL_INTERVAL_SECONDS)
                
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            if current_job:
                update_job_status(current_job["id"], "failed", error=str(e))
                current_job = None
            time.sleep(5)

if __name__ == "__main__":
    main()
```

### 3. 測試

```bash
# 啟動 Worker
python main.py

# 觀察日誌輸出
# 應該看到 Worker 註冊成功，然後開始輪詢作業
```

## 🧪 測試清單

- [ ] Worker 成功註冊到 API
- [ ] 心跳回報正常運作
- [ ] 成功領取 `character_analysis` 作業
- [ ] 成功領取 `story_generation` 作業
- [ ] 成功領取 `script_generation` 作業
- [ ] 成功領取 `scene_json_generation` 作業
- [ ] LLM API 呼叫成功
- [ ] JSON 回應解析正確
- [ ] 作業狀態正確回報
- [ ] 錯誤處理與重試機制正常

## 🔍 除錯技巧

### 查看 Worker 狀態
```bash
# 檢查 Worker 是否註冊
curl http://localhost:8000/workers

# 檢查作業佇列
curl http://localhost:8000/projects/{project_id}/jobs
```

### 測試 LLM API
```python
# 測試 OpenAI API
import openai
client = openai.OpenAI(api_key="your-key")
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello"}]
)
print(response.choices[0].message.content)
```

## 📚 相關文件

- [Worker 架構總覽](./ARCHITECTURE.md)
- [Orchestrator 開發指南](./ORCHESTRATOR.md)
- [Worker 通訊協定](./WORKER_PROTOCOL.md)

---

**版本**: 1.0.0  
**最後更新**: 2026-08-10
