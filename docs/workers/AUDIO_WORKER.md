# Audio Worker - 開發指南 (F5-TTS / Whisper)

## 📋 概述

Audio Worker 負責所有音訊生成與處理任務，使用 F5-TTS 進行語音合成、Whisper 進行語音辨識，以及背景音樂生成。這是 AI 動漫工作室的音訊處理引擎。

**硬體需求**: RTX 5060 Ti 8GB VRAM

---

## 🎯 職責

| 作業類型 | 說明 | 輸入 | 輸出 |
|---------|------|------|------|
| `voice_synthesis` | 生成角色語音 | text, voice_config | audio_url, metadata |
| `voice_recognition` | 語音轉文字 | audio_url | text, timestamps |
| `bgm_generation` | 生成背景音樂 | mood, genre, duration | audio_url, metadata |
| `sfx_generation` | 生成音效 | effect_type, description | audio_url, metadata |
| `audio_mixing` | 音訊混音 | dialogue, bgm, sfx | audio_url, metadata |

---

## 🏗️ 系統架構

```
┌─────────────────────────────────────────────────────────────┐
│                    Audio Worker Loop                         │
│                                                               │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────────┐   │
│  │ 1.Register│──►│ 2.Claim  │──►│ 3. Load Audio Model   │   │
│  │  (註冊)    │    │  (領取)   │    │  (載入 TTS/Whisper)   │   │
│  └──────────┘    └──────────┘    └──────────┬───────────┘   │
│                                             │                │
│  ┌──────────┐    ┌──────────┐    ┌─────────▼──────────┐    │
│  │ 5.Heartbeat│◄─│ 4.Upload │◄─│ 4. Generate & Upload │    │
│  │  (心跳)    │    │  (上傳)   │    │  (生成並上傳)        │    │
│  └──────────┘    └──────────┘    └────────────────────┘    │
│                                                               │
│  VRAM 管理: 模型切換、音訊快取、批次處理                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 硬體需求

| 項目 | 最低需求 | 建議配置 |
|------|---------|---------|
| **GPU** | RTX 5060 Ti | RTX 5060 Ti 8GB |
| **VRAM** | 6GB | 8GB |
| **CPU** | 4 核心 | 8 核心 |
| **RAM** | 16GB | 32GB |
| **儲存** | 200GB SSD | 500GB NVMe SSD |
| **網路** | 100Mbps | 1Gbps |

---

## 📦 依賴套件

```txt
# requirements.txt
torch>=2.1.0
torchaudio>=2.1.0
f5-tts>=0.1.0
openai-whisper>=20231117
transformers>=4.37.0
soundfile>=0.12.1
pydub>=0.25.1
minio>=7.2.0
requests>=2.31.0
numpy>=1.24.0
librosa>=0.10.1
scipy>=1.11.0
```

**Docker 基礎映像**: `nvidia/cuda:12.4.1-devel-ubuntu22.04`

---

## 🔧 環境變數

| 變數名稱 | 說明 | 預設值 |
|---------|------|--------|
| `API_BASE_URL` | API 服務位址 | `http://api:8000` |
| `WORKER_ID` | Worker 唯一識別碼 | `audio-01` |
| `WORKER_TYPE` | Worker 類型 | `audio` |
| `WORKER_HOSTNAME` | Worker 主機名稱 | `audio-worker` |
| `WORKER_CAPABILITIES` | 支援的作業類型 | `voice_synthesis,voice_recognition,bgm_generation` |
| `POLL_INTERVAL_SECONDS` | 輪詢間隔 (秒) | `5` |
| `S3_ENDPOINT` | MinIO/S3 端點 | `http://minio:9000` |
| `S3_ACCESS_KEY` | S3 存取金鑰 | `minioadmin` |
| `S3_SECRET_KEY` | S3 秘密金鑰 | `minioadmin123` |
| `S3_BUCKET` | S3 Bucket 名稱 | `assets` |
| `F5_TTS_MODEL_PATH` | F5-TTS 模型路徑 | `/models/f5-tts/base` |
| `WHISPER_MODEL_SIZE` | Whisper 模型大小 | `medium` |
| `SAMPLE_RATE` | 取樣率 (Hz) | `44100` |
| `AUDIO_FORMAT` | 音訊格式 | `wav` |
| `VOICE_CLONE_ENABLED` | 啟用語音克隆 | `true` |
| `BGM_MODEL_PATH` | BGM 生成模型路徑 | `/models/bgm/musicgen` |

---

## 📝 核心函式說明

### 1. Worker 註冊

```python
def register_worker() -> None:
    """
    向 API 註冊 Audio Worker
    
    Request:
    POST /worker/register
    {
        "worker_id": "audio-01",
        "worker_type": "audio",
        "hostname": "audio-worker",
        "capabilities": ["voice_synthesis", "voice_recognition", "bgm_generation"],
        "models": ["f5-tts-v1", "whisper-medium"]
    }
    
    Response: 200 OK
    """
    payload = {
        "worker_id": WORKER_ID,
        "worker_type": WORKER_TYPE,
        "hostname": WORKER_HOSTNAME,
        "capabilities": WORKER_CAPABILITIES,
        "models": ["f5-tts-v1", "whisper-medium"],
    }
    response = requests.post(f"{API_BASE_URL}/worker/register", json=payload, timeout=10)
    response.raise_for_status()
```

### 2. 領取作業

```python
def claim_job() -> dict | None:
    """
    從佇列領取下一個音訊處理作業
    
    Request:
    POST /worker/jobs/claim
    {"worker_id": "audio-01"}
    
    Response:
    - 200: {"job_id": "...", "type": "voice_synthesis", "input": {...}}
    - 404: 沒有可用作業
    """
    response = requests.post(
        f"{API_BASE_URL}/worker/jobs/claim",
        json={"worker_id": WORKER_ID},
        timeout=10,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()
```

### 3. 語音合成 (F5-TTS)

```python
def synthesize_voice(text: str, voice_config: dict) -> str:
    """
    生成角色語音
    
    Args:
        text: 要合成的文字
        voice_config: {
            "character_id": "char_001",
            "voice_type": "female_young",
            "emotion": "happy",
            "speed": 1.0,
            "pitch": 0,
            "reference_audio_url": "minio_url_to_reference.wav" (optional)
        }
    
    Returns:
        audio_url: MinIO 上的音訊 URL
    
    流程:
    1. 載入 F5-TTS 模型
    2. 如果有 reference_audio，進行語音克隆
    3. 生成語音
    4. 後處理 (音量調整、雜訊去除)
    5. 上傳到 MinIO
    6. 回傳 URL
    """
    from f5_tts import F5TTS
    
    # 1. 載入模型
    tts = F5TTS.from_pretrained(F5_TTS_MODEL_PATH)
    tts = tts.to("cuda")
    
    # 2. 準備參考音訊 (如果有)
    reference_audio_path = None
    if voice_config.get("reference_audio_url"):
        reference_audio_path = download_from_s3(voice_config["reference_audio_url"])
    
    # 3. 生成語音
    audio = tts.generate(
        text=text,
        voice_type=voice_config.get("voice_type", "female_young"),
        emotion=voice_config.get("emotion", "neutral"),
        speed=voice_config.get("speed", 1.0),
        pitch_shift=voice_config.get("pitch", 0),
        reference_audio=reference_audio_path,
    )
    
    # 4. 後處理
    audio_path = f"/tmp/voice_{uuid4().hex}.wav"
    save_audio(audio, audio_path, sample_rate=SAMPLE_RATE)
    normalize_audio(audio_path)
    
    # 5. 上傳到 MinIO
    object_name = f"audio/dialogue/{voice_config['character_id']}/{uuid4().hex}.wav"
    audio_url = upload_to_s3(audio_path, object_name)
    
    # 清理
    cleanup([audio_path])
    if reference_audio_path:
        cleanup([reference_audio_path])
    torch.cuda.empty_cache()
    
    return audio_url
```

### 4. 語音辨識 (Whisper)

```python
def recognize_speech(audio_url: str) -> dict:
    """
    語音轉文字
    
    Args:
        audio_url: MinIO 上的音訊 URL
    
    Returns:
        {
            "text": "辨識出的文字",
            "segments": [
                {"start": 0.0, "end": 1.5, "text": "第一段文字"},
                {"start": 1.5, "end": 3.0, "text": "第二段文字"}
            ],
            "language": "zh"
        }
    
    流程:
    1. 下載音訊檔案
    2. 載入 Whisper 模型
    3. 執行語音辨識
    4. 回傳文字與時間戳記
    """
    import whisper
    
    # 1. 下載音訊
    audio_path = download_from_s3(audio_url)
    
    # 2. 載入模型
    model = whisper.load_model(WHISPER_MODEL_SIZE)
    
    # 3. 執行辨識
    result = model.transcribe(
        audio_path,
        language="zh",  # 或 auto
        verbose=False,
    )
    
    # 4. 整理結果
    output = {
        "text": result["text"],
        "segments": [
            {
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"]
            }
            for seg in result["segments"]
        ],
        "language": result.get("language", "zh")
    }
    
    # 清理
    cleanup([audio_path])
    
    return output
```

### 5. 背景音樂生成

```python
def generate_bgm(mood: str, genre: str, duration: float) -> str:
    """
    生成背景音樂
    
    Args:
        mood: 情緒 (happy, sad, tense, romantic, etc.)
        genre: 類型 (anime, orchestral, electronic, etc.)
        duration: 持續時間 (秒)
    
    Returns:
        audio_url: MinIO 上的 BGM URL
    
    流程:
    1. 載入 MusicGen 模型
    2. 建構 prompt
    3. 生成音樂
    4. 調整長度
    5. 上傳到 MinIO
    """
    from transformers import AutoProcessor, MusicgenForConditionalGeneration
    
    # 1. 載入模型
    processor = AutoProcessor.from_pretrained(BGM_MODEL_PATH)
    model = MusicgenForConditionalGeneration.from_pretrained(BGM_MODEL_PATH)
    model = model.to("cuda")
    
    # 2. 建構 prompt
    prompt = f"{mood} {genre} anime background music, instrumental, no vocals"
    
    # 3. 生成音樂
    inputs = processor(prompt, return_tensors="pt").to("cuda")
    audio_values = model.generate(
        **inputs,
        max_new_tokens=int(duration * model.config.audio_encoder.frame_rate),
    )
    
    # 4. 儲存
    audio_path = f"/tmp/bgm_{uuid4().hex}.wav"
    import soundfile as sf
    sf.write(audio_path, audio_values.cpu().numpy(), samplerate=SAMPLE_RATE)
    
    # 5. 上傳
    object_name = f"audio/bgm/{mood}_{genre}_{duration}s_{uuid4().hex}.wav"
    audio_url = upload_to_s3(audio_path, object_name)
    
    cleanup([audio_path])
    torch.cuda.empty_cache()
    
    return audio_url
```

### 6. 音訊混音

```python
def mix_audio(dialogue_url: str, bgm_url: str, sfx_urls: list[str]) -> str:
    """
    混音對話、背景音樂和音效
    
    Args:
        dialogue_url: 對話音訊 URL
        bgm_url: 背景音樂 URL
        sfx_urls: 音效 URL 列表
    
    Returns:
        audio_url: MinIO 上的混音結果 URL
    
    流程:
    1. 下載所有音訊檔案
    2. 調整 BGM 音量 (降低以避免掩蓋對話)
    3. 混合所有音軌
    4. 上傳結果
    """
    from pydub import AudioSegment
    
    # 1. 下載所有音訊
    dialogue_path = download_from_s3(dialogue_url)
    bgm_path = download_from_s3(bgm_url)
    sfx_paths = [download_from_s3(url) for url in sfx_urls]
    
    # 2. 載入音訊
    dialogue = AudioSegment.from_wav(dialogue_path)
    bgm = AudioSegment.from_wav(bgm_path)
    
    # 3. 調整 BGM 音量 (降低 20dB)
    bgm = bgm - 20
    
    # 4. 延長 BGM 以匹配對話長度
    if len(bgm) < len(dialogue):
        bgm = bgm[:len(dialogue)]
    else:
        bgm = bgm[:len(dialogue)]
    
    # 5. 混合
    mixed = dialogue.overlay(bgm)
    
    # 6. 加入音效
    for sfx_path in sfx_paths:
        sfx = AudioSegment.from_wav(sfx_path)
        mixed = mixed.overlay(sfx)
    
    # 7. 儲存
    output_path = f"/tmp/mixed_{uuid4().hex}.wav"
    mixed.export(output_path, format="wav")
    
    # 8. 上傳
    object_name = f"audio/mixed/{uuid4().hex}.wav"
    audio_url = upload_to_s3(output_path, object_name)
    
    # 清理
    cleanup([dialogue_path, bgm_path, *sfx_paths, output_path])
    
    return audio_url
```

### 7. VRAM 管理

```python
def manage_vram() -> None:
    """
    VRAM 管理策略
    
    音訊模型相對較小，但仍需管理
    """
    import torch
    
    free_vram = torch.cuda.mem_get_info()[0] / 1024**3  # GB
    
    if free_vram < 2:  # 少於 2GB
        torch.cuda.empty_cache()
```

---

## 🎵 F5-TTS 使用範例

### 基本語音合成

```python
from f5_tts import F5TTS

# 載入模型
tts = F5TTS.from_pretrained("f5-tts/base")
tts = tts.to("cuda")

# 生成語音
audio = tts.generate(
    text="你好，我是你的動漫角色。",
    voice_type="female_young",
    emotion="happy",
    speed=1.0,
)

# 儲存
import soundfile as sf
sf.write("output.wav", audio, samplerate=44100)
```

### 語音克隆

```python
from f5_tts import F5TTS

# 載入模型
tts = F5TTS.from_pretrained("f5-tts/base")
tts = tts.to("cuda")

# 使用參考音訊進行克隆
audio = tts.generate(
    text="用相同的聲音說這段話。",
    reference_audio="reference.wav",  # 3-10 秒的參考音訊
)

# 儲存
import soundfile as sf
sf.write("cloned.wav", audio, samplerate=44100)
```

---

## 🔄 Worker 主循環

```python
def loop() -> None:
    """Audio Worker 主循環"""
    print(f"[{datetime.now().isoformat()}] Audio Worker starting...")
    print(f"  WORKER_ID: {WORKER_ID}")
    print(f"  F5_TTS_MODEL_PATH: {F5_TTS_MODEL_PATH}")
    print(f"  CAPABILITIES: {WORKER_CAPABILITIES}")
    
    # 註冊
    register_worker()
    send_heartbeat(status="idle", current_job=None)
    
    while True:
        try:
            # 領取作業
            job = claim_job()
            
            if job is None:
                send_heartbeat(status="idle", current_job=None)
                time.sleep(POLL_INTERVAL_SECONDS)
                continue
            
            job_id = job["job_id"]
            job_type = job["type"]
            input_data = job.get("input", {})
            
            # 更新狀態為 running
            send_heartbeat(status="busy", current_job=job_id)
            update_job_status(job_id=job_id, status="running", progress=0.1)
            
            # VRAM 管理
            manage_vram()
            
            # 執行處理
            if job_type == "voice_synthesis":
                audio_url = synthesize_voice(
                    input_data.get("text", ""),
                    input_data.get("voice_config", {})
                )
                result = {"audio_url": audio_url, "type": "dialogue"}
                
            elif job_type == "voice_recognition":
                recognition_result = recognize_speech(
                    input_data.get("audio_url", "")
                )
                result = {"text": recognition_result["text"], "type": "transcription"}
                
            elif job_type == "bgm_generation":
                audio_url = generate_bgm(
                    input_data.get("mood", "neutral"),
                    input_data.get("genre", "anime"),
                    input_data.get("duration", 30.0)
                )
                result = {"audio_url": audio_url, "type": "bgm"}
                
            elif job_type == "audio_mixing":
                audio_url = mix_audio(
                    input_data.get("dialogue_url", ""),
                    input_data.get("bgm_url", ""),
                    input_data.get("sfx_urls", [])
                )
                result = {"audio_url": audio_url, "type": "mixed"}
                
            else:
                raise ValueError(f"Unsupported audio job type: {job_type}")
            
            # 更新為 completed
            update_job_status(
                job_id=job_id,
                status="completed",
                progress=1.0,
                result={
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "output": result,
                },
            )
            
        except Exception as e:
            print(f"[ERROR] Job failed: {e}")
            if "job_id" in locals():
                update_job_status(job_id=job_id, status="failed", error=str(e))
            
            time.sleep(5)
        
        finally:
            send_heartbeat(status="idle", current_job=None)
```

---

## 📊 效能最佳化

### 1. 模型快取

```python
# 預載入 TTS 和 Whisper 模型
TTS_MODEL = None
WHISPER_MODEL = None

def get_tts_model():
    global TTS_MODEL
    if TTS_MODEL is None:
        from f5_tts import F5TTS
        TTS_MODEL = F5TTS.from_pretrained(F5_TTS_MODEL_PATH)
        TTS_MODEL = TTS_MODEL.to("cuda")
    return TTS_MODEL

def get_whisper_model():
    global WHISPER_MODEL
    if WHISPER_MODEL is None:
        import whisper
        WHISPER_MODEL = whisper.load_model(WHISPER_MODEL_SIZE)
    return WHISPER_MODEL
```

### 2. 批次語音合成

```python
def batch_synthesize(dialogues: list[dict]) -> list[str]:
    """批次生成多個對話"""
    tts = get_tts_model()
    
    audio_urls = []
    for dialogue in dialogues:
        audio = tts.generate(
            text=dialogue["text"],
            voice_type=dialogue.get("voice_type", "female_young"),
            emotion=dialogue.get("emotion", "neutral"),
        )
        
        audio_path = f"/tmp/voice_{uuid4().hex}.wav"
        save_audio(audio, audio_path, sample_rate=SAMPLE_RATE)
        
        object_name = f"audio/dialogue/{dialogue['character_id']}/{uuid4().hex}.wav"
        audio_url = upload_to_s3(audio_path, object_name)
        
        audio_urls.append(audio_url)
        cleanup([audio_path])
    
    return audio_urls
```

---

## 🧪 測試清單

- [ ] Worker 註冊成功
- [ ] 心跳正常發送
- [ ] 領取 `voice_synthesis` 作業
- [ ] 生成語音並上傳 MinIO
- [ ] 領取 `voice_recognition` 作業
- [ ] 執行語音辨識並回傳文字
- [ ] 領取 `bgm_generation` 作業
- [ ] 生成背景音樂並上傳 MinIO
- [ ] 領取 `audio_mixing` 作業
- [ ] 混音並上傳結果
- [ ] VRAM 不足時正確處理
- [ ] 錯誤時正確回報狀態

---

## 🔗 相關文件

- [WORKER_PROTOCOL.md](./WORKER_PROTOCOL.md) - API 協定規格
- [VIDEO_WORKER.md](./VIDEO_WORKER.md) - Video Worker (前置依賴)
- [EDITOR_WORKER.md](./EDITOR_WORKER.md) - Editor Worker (後續依賴)
- [ORCHESTRATOR.md](./ORCHESTRATOR.md) - 工作流程協調器

---

**版本**: 1.0.0  
**最後更新**: 2026-08-10  
**硬體**: RTX 5060 Ti 8GB
