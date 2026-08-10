# Editor Worker - 開發指南 (FFmpeg)

## 📋 概述

Editor Worker 負責最終的影片合成與編輯，使用 FFmpeg 將影像、影片、音訊和字幕整合為最終的 MP4 輸出。這是 AI 動漫工作室的最後一道製程，將所有生成的素材組合成完整的動漫影片。

**硬體需求**: CPU 密集型，GPU 可選 (用於硬體編碼)

---

## 🎯 職責

| 作業類型 | 說明 | 輸入 | 輸出 |
|---------|------|------|------|
| `video_composition` | 合成場景影片 | scene_video, bgm, dialogue, subtitles | composed_video_url |
| `final_render` | 最終渲染整集 | all_scene_videos, transitions, credits | final_episode_mp4_url |
| `subtitle_burn` | 嵌入字幕 | video_url, subtitle_file | video_with_subs_url |
| `video_resize` | 調整影片解析度 | video_url, target_resolution | resized_video_url |
| `video_concat` | 串接多個影片 | video_urls[] | concatenated_video_url |
| `audio_sync` | 音訊同步調整 | video_url, audio_url | synced_video_url |

---

## 🏗️ 系統架構

```
┌─────────────────────────────────────────────────────────────┐
│                    Editor Worker Loop                        │
│                                                               │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────────┐   │
│  │ 1.Register│──►│ 2.Claim  │──►│ 3. Download Assets    │   │
│  │  (註冊)    │    │  (領取)   │    │  (下載所有素材)        │   │
│  └──────────┘    └──────────┘    └──────────┬───────────┘   │
│                                             │                │
│  ┌──────────┐    ┌──────────┐    ┌─────────▼──────────┐    │
│  │ 5.Heartbeat│◄─│ 4.Upload │◄─│ 4. Compose & Upload  │    │
│  │  (心跳)    │    │  (上傳)   │    │  (合成並上傳)        │    │
│  └──────────┘    └──────────┘    └────────────────────┘    │
│                                                               │
│  資源管理: 暫存空間清理、並行處理、硬體編碼加速                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 硬體需求

| 項目 | 最低需求 | 建議配置 |
|------|---------|---------|
| **CPU** | 8 核心 | 16 核心 (Intel i7 / AMD Ryzen 7) |
| **RAM** | 32GB | 64GB |
| **儲存** | 500GB SSD | 1TB NVMe SSD |
| **GPU** | 可選 | RTX 5060+ (用於硬體編碼) |
| **網路** | 100Mbps | 1Gbps |

**注意**: Editor Worker 主要依賴 CPU，但如果有 GPU 可以使用 NVENC 硬體編碼加速。

---

## 📦 依賴套件

```txt
# requirements.txt
ffmpeg-python>=0.2.0
minio>=7.2.0
requests>=2.31.0
numpy>=1.12.0
Pillow>=10.0.0
python-dotenv>=1.0.0
```

**系統依賴**:
```bash
# Ubuntu/Debian
sudo apt-get install -y ffmpeg

# 驗證安裝
ffmpeg -version
```

**Docker 基礎映像**: `python:3.11-slim` (安裝 FFmpeg)

---

## 🔧 環境變數

| 變數名稱 | 說明 | 預設值 |
|---------|------|--------|
| `API_BASE_URL` | API 服務位址 | `http://api:8000` |
| `WORKER_ID` | Worker 唯一識別碼 | `editor-01` |
| `WORKER_TYPE` | Worker 類型 | `editor` |
| `WORKER_HOSTNAME` | Worker 主機名稱 | `editor-worker` |
| `WORKER_CAPABILITIES` | 支援的作業類型 | `video_composition,final_render,subtitle_burn` |
| `POLL_INTERVAL_SECONDS` | 輪詢間隔 (秒) | `5` |
| `S3_ENDPOINT` | MinIO/S3 端點 | `http://minio:9000` |
| `S3_ACCESS_KEY` | S3 存取金鑰 | `minioadmin` |
| `S3_SECRET_KEY` | S3 秘密金鑰 | `minioadmin123` |
| `S3_BUCKET` | S3 Bucket 名稱 | `assets` |
| `TEMP_DIR` | 暫存目錄 | `/tmp/editor` |
| `MAX_CONCURRENT_JOBS` | 最大並行作業數 | `2` |
| `VIDEO_CODEC` | 影片編碼器 | `libx264` |
| `AUDIO_CODEC` | 音訊編碼器 | `aac` |
| `VIDEO_BITRATE` | 影片位元率 | `5000k` |
| `AUDIO_BITRATE` | 音訊位元率 | `192k` |
| `OUTPUT_FPS` | 輸出幀率 | `24` |
| `OUTPUT_WIDTH` | 輸出寬度 | `1920` |
| `OUTPUT_HEIGHT` | 輸出高度 | `1080` |
| `USE_HW_ENCODING` | 使用硬體編碼 | `false` |

---

## 📝 核心函式說明

### 1. Worker 註冊

```python
def register_worker() -> None:
    """
    向 API 註冊 Editor Worker
    
    Request:
    POST /worker/register
    {
        "worker_id": "editor-01",
        "worker_type": "editor",
        "hostname": "editor-worker",
        "capabilities": ["video_composition", "final_render", "subtitle_burn"],
        "models": ["ffmpeg-6.0"]
    }
    
    Response: 200 OK
    """
    payload = {
        "worker_id": WORKER_ID,
        "worker_type": WORKER_TYPE,
        "hostname": WORKER_HOSTNAME,
        "capabilities": WORKER_CAPABILITIES,
        "models": ["ffmpeg-6.0"],
    }
    response = requests.post(f"{API_BASE_URL}/worker/register", json=payload, timeout=10)
    response.raise_for_status()
```

### 2. 領取作業

```python
def claim_job() -> dict | None:
    """
    從佇列領取下一個編輯作業
    
    Request:
    POST /worker/jobs/claim
    {"worker_id": "editor-01"}
    
    Response:
    - 200: {"job_id": "...", "type": "video_composition", "input": {...}}
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

### 3. 場景影片合成

```python
def compose_scene_video(
    scene_video_url: str,
    bgm_url: str | None,
    dialogue_url: str | None,
    subtitle_url: str | None,
    output_duration: float | None = None
) -> str:
    """
    合成場景影片 (影片 + 背景音樂 + 對話 + 字幕)
    
    Args:
        scene_video_url: MinIO 上的場景影片 URL
        bgm_url: MinIO 上的背景音樂 URL (optional)
        dialogue_url: MinIO 上的對話音訊 URL (optional)
        subtitle_url: MinIO 上的字幕檔案 URL (optional)
        output_duration: 輸出影片長度 (秒) (optional)
    
    Returns:
        composed_video_url: MinIO 上的合成影片 URL
    
    流程:
    1. 下載所有素材
    2. 建構 FFmpeg 命令
    3. 執行合成
    4. 上傳結果
    5. 清理暫存檔案
    """
    import ffmpeg
    import os
    
    # 1. 下載所有素材
    video_path = download_from_s3(scene_video_url)
    bgm_path = download_from_s3(bgm_url) if bgm_url else None
    dialogue_path = download_from_s3(dialogue_url) if dialogue_url else None
    subtitle_path = download_from_s3(subtitle_url) if subtitle_url else None
    
    # 2. 建構 FFmpeg 輸入
    input_video = ffmpeg.input(video_path)
    
    # 3. 處理音訊軌
    audio_inputs = [input_video.audio]
    
    if bgm_path:
        bgm_input = ffmpeg.input(bgm_path)
        # 降低 BGM 音量
        bgm_faded = bgm_input.filter('volume', 0.3)
        audio_inputs.append(bgm_faded)
    
    if dialogue_path:
        dialogue_input = ffmpeg.input(dialogue_path)
        audio_inputs.append(dialogue_input)
    
    # 混合音訊
    if len(audio_inputs) > 1:
        mixed_audio = ffmpeg.filter_(audio_inputs, 'amix', inputs=len(audio_inputs), duration='longest')
    else:
        mixed_audio = audio_inputs[0]
    
    # 4. 合成影片
    output_path = f"{TEMP_DIR}/composed_{uuid4().hex}.mp4"
    
    process = (
        ffmpeg
        .output(
            input_video,
            mixed_audio,
            output_path,
            v=VIDEO_CODEC,
            ac=AUDIO_CODEC,
            b:v=VIDEO_BITRATE,
            b:a=AUDIO_BITRATE,
            r=OUTPUT_FPS,
            s=f"{OUTPUT_WIDTH}x{OUTPUT_HEIGHT}",
            # 字幕處理
            vf=f"subtitles={subtitle_path}" if subtitle_path else None,
        )
        .overwrite_output()
    )
    
    # 5. 執行 FFmpeg
    process.run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
    
    # 6. 上傳結果
    object_name = f"videos/composed/{uuid4().hex}.mp4"
    composed_video_url = upload_to_s3(output_path, object_name)
    
    # 7. 清理
    cleanup([video_path, output_path])
    if bgm_path:
        cleanup([bgm_path])
    if dialogue_path:
        cleanup([dialogue_path])
    if subtitle_path:
        cleanup([subtitle_path])
    
    return composed_video_url
```

### 4. 最終渲染 (整集)

```python
def final_render_episode(
    scene_videos: list[dict],
    transition_type: str = "fade",
    transition_duration: float = 1.0,
    credits_text: str | None = None,
) -> str:
    """
    最終渲染整集影片
    
    Args:
        scene_videos: [
            {
                "video_url": "minio_url_to_scene_1.mp4",
                "duration": 6.0,
                "order": 1
            },
            {
                "video_url": "minio_url_to_scene_2.mp4",
                "duration": 8.0,
                "order": 2
            },
            ...
        ]
        transition_type: 轉換效果 (fade, dissolve, wipe, none)
        transition_duration: 轉換持續時間 (秒)
        credits_text: 片尾字幕文字 (optional)
    
    Returns:
        final_episode_url: MinIO 上的最終影片 URL
    
    流程:
    1. 下載所有場景影片
    2. 按順序排列
    3. 產生轉換效果
    4. 串接所有場景
    5. 加入片尾字幕
    6. 最終編碼
    7. 上傳結果
    """
    import ffmpeg
    import os
    
    # 1. 下載並排序所有場景影片
    downloaded_paths = []
    for scene in sorted(scene_videos, key=lambda x: x["order"]):
        video_path = download_from_s3(scene["video_url"])
        downloaded_paths.append((video_path, scene["duration"]))
    
    # 2. 建立串接清單
    concat_list_path = f"{TEMP_DIR}/concat_list_{uuid4().hex}.txt"
    with open(concat_list_path, "w") as f:
        for video_path, duration in downloaded_paths:
            if transition_type != "none":
                # 每個影片減去轉換時間
                actual_duration = duration - transition_duration
                f.write(f"file '{video_path}'\n")
                f.write(f"inpoint 0\n")
                f.write(f"outpoint {actual_duration}\n")
            else:
                f.write(f"file '{video_path}'\n")
    
    # 3. 串接影片
    concatenated_path = f"{TEMP_DIR}/concatenated_{uuid4().hex}.mp4"
    
    (
        ffmpeg
        .input(concat_list_path, format='concat', safe=0)
        .output(
            concatenated_path,
            v=VIDEO_CODEC,
            ac=AUDIO_CODEC,
            b:v=VIDEO_BITRATE,
            b:a=AUDIO_BITRATE,
            r=OUTPUT_FPS,
            s=f"{OUTPUT_WIDTH}x{OUTPUT_HEIGHT}",
            c:v='libx264' if not USE_HW_ENCODING else 'h264_nvenc',
            preset='medium',
            crf=23,
        )
        .overwrite_output()
        .run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
    )
    
    # 4. 加入片尾字幕 (如果有)
    final_path = concatenated_path
    if credits_text:
        final_path = f"{TEMP_DIR}/final_{uuid4().hex}.mp4"
        credits_srt = create_credits_srt(credits_text)
        
        (
            ffmpeg
            .input(concatenated_path)
            .output(
                final_path,
                vf=f"subtitles={credits_srt}",
                c:v=VIDEO_CODEC,
                c:a=AUDIO_CODEC,
            )
            .overwrite_output()
            .run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
        )
        cleanup([credits_srt])
    
    # 5. 上傳結果
    object_name = f"episodes/final/{uuid4().hex}.mp4"
    final_episode_url = upload_to_s3(final_path, object_name)
    
    # 6. 清理
    cleanup([video_path for video_path, _ in downloaded_paths])
    cleanup([concat_list_path, concatenated_path])
    if final_path != concatenated_path:
        cleanup([final_path])
    
    return final_episode_url
```

### 5. 嵌入字幕

```python
def burn_subtitles(video_url: str, subtitle_url: str) -> str:
    """
    將字幕嵌入影片
    
    Args:
        video_url: MinIO 上的影片 URL
        subtitle_url: MinIO 上的字幕檔案 URL (.srt, .ass)
    
    Returns:
        video_with_subs_url: MinIO 上的嵌入字幕影片 URL
    """
    import ffmpeg
    
    # 下載素材
    video_path = download_from_s3(video_url)
    subtitle_path = download_from_s3(subtitle_url)
    
    # 嵌入字幕
    output_path = f"{TEMP_DIR}/subtitled_{uuid4().hex}.mp4"
    
    (
        ffmpeg
        .input(video_path)
        .output(
            output_path,
            vf=f"subtitles={subtitle_path}",
            c:v=VIDEO_CODEC,
            c:a='copy',  # 複製音訊軌，不重新編碼
        )
        .overwrite_output()
        .run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
    )
    
    # 上傳
    object_name = f"videos/subtitled/{uuid4().hex}.mp4"
    video_with_subs_url = upload_to_s3(output_path, object_name)
    
    # 清理
    cleanup([video_path, subtitle_path, output_path])
    
    return video_with_subs_url
```

### 6. 影片串接

```python
def concat_videos(video_urls: list[str]) -> str:
    """
    串接多個影片
    
    Args:
        video_urls: MinIO 上的影片 URL 列表
    
    Returns:
        concatenated_video_url: MinIO 上的串接影片 URL
    """
    import ffmpeg
    
    # 下載所有影片
    downloaded_paths = [download_from_s3(url) for url in video_urls]
    
    # 建立串接清單
    concat_list_path = f"{TEMP_DIR}/concat_list_{uuid4().hex}.txt"
    with open(concat_list_path, "w") as f:
        for path in downloaded_paths:
            f.write(f"file '{path}'\n")
    
    # 串接
    output_path = f"{TEMP_DIR}/concatenated_{uuid4().hex}.mp4"
    
    (
        ffmpeg
        .input(concat_list_path, format='concat', safe=0)
        .output(
            output_path,
            c:v=VIDEO_CODEC,
            c:a=AUDIO_CODEC,
            movflags='+faststart',  # 優化網路串流
        )
        .overwrite_output()
        .run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
    )
    
    # 上傳
    object_name = f"videos/concatenated/{uuid4().hex}.mp4"
    concatenated_video_url = upload_to_s3(output_path, object_name)
    
    # 清理
    cleanup(downloaded_paths + [concat_list_path, output_path])
    
    return concatenated_video_url
```

### 7. 音訊同步

```python
def sync_audio(video_url: str, audio_url: str) -> str:
    """
    將音訊與影片同步
    
    Args:
        video_url: MinIO 上的影片 URL
        audio_url: MinIO 上的音訊 URL
    
    Returns:
        synced_video_url: MinIO 上的同步影片 URL
    """
    import ffmpeg
    
    # 下載素材
    video_path = download_from_s3(video_url)
    audio_path = download_from_s3(audio_url)
    
    # 同步
    output_path = f"{TEMP_DIR}/synced_{uuid4().hex}.mp4"
    
    (
        ffmpeg
        .input(video_path)
        .input(audio_path)
        .output(
            output_path,
            v=VIDEO_CODEC,
            ac=AUDIO_CODEC,
            map=[0, 1],  # 映射影片和音訊
            shortest=True,  # 以最短的軌為基準
        )
        .overwrite_output()
        .run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
    )
    
    # 上傳
    object_name = f"videos/synced/{uuid4().hex}.mp4"
    synced_video_url = upload_to_s3(output_path, object_name)
    
    # 清理
    cleanup([video_path, audio_path, output_path])
    
    return synced_video_url
```

---

## 🎬 FFmpeg 命令範例

### 基本影片合成

```bash
# 合成影片 + 音訊 + 字幕
ffmpeg \
  -i scene_video.mp4 \
  -i bgm.wav \
  -i dialogue.wav \
  -filter_complex \
    "[1:a]volume=0.3[bgm]; \
     [2:a]volume=1.0[dialogue]; \
     [bgm][dialogue]amix=inputs=2:duration=longest[a]" \
  -c:v libx264 \
  -c:a aac \
  -b:v 5000k \
  -b:a 192k \
  -r 24 \
  -s 1920x1080 \
  -vf "subtitles=subtitle.srt" \
  -y output.mp4
```

### 硬體編碼 (NVENC)

```bash
# 使用 NVIDIA GPU 硬體編碼
ffmpeg \
  -i input.mp4 \
  -c:v h264_nvenc \
  -preset p4 \
  -rc vbr \
  -cq 23 \
  -c:a aac \
  -b:a 192k \
  -y output.mp4
```

### 影片串接

```bash
# 建立串接清單
echo "file 'scene1.mp4'" > concat_list.txt
echo "file 'scene2.mp4'" >> concat_list.txt
echo "file 'scene3.mp4'" >> concat_list.txt

# 執行串接
ffmpeg -f concat -safe 0 -i concat_list.txt -c copy output.mp4
```

---

## 🔄 Worker 主循環

```python
def loop() -> None:
    """Editor Worker 主循環"""
    print(f"[{datetime.now().isoformat()}] Editor Worker starting...")
    print(f"  WORKER_ID: {WORKER_ID}")
    print(f"  TEMP_DIR: {TEMP_DIR}")
    print(f"  CAPABILITIES: {WORKER_CAPABILITIES}")
    
    # 建立暫存目錄
    os.makedirs(TEMP_DIR, exist_ok=True)
    
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
            
            # 執行編輯
            if job_type == "video_composition":
                video_url = compose_scene_video(
                    scene_video_url=input_data.get("scene_video_url"),
                    bgm_url=input_data.get("bgm_url"),
                    dialogue_url=input_data.get("dialogue_url"),
                    subtitle_url=input_data.get("subtitle_url"),
                    output_duration=input_data.get("output_duration"),
                )
                result = {"video_url": video_url, "type": "composed"}
                
            elif job_type == "final_render":
                video_url = final_render_episode(
                    scene_videos=input_data.get("scene_videos", []),
                    transition_type=input_data.get("transition_type", "fade"),
                    transition_duration=input_data.get("transition_duration", 1.0),
                    credits_text=input_data.get("credits_text"),
                )
                result = {"video_url": video_url, "type": "final_episode"}
                
            elif job_type == "subtitle_burn":
                video_url = burn_subtitles(
                    video_url=input_data.get("video_url"),
                    subtitle_url=input_data.get("subtitle_url"),
                )
                result = {"video_url": video_url, "type": "subtitled"}
                
            elif job_type == "video_concat":
                video_url = concat_videos(
                    video_urls=input_data.get("video_urls", [])
                )
                result = {"video_url": video_url, "type": "concatenated"}
                
            elif job_type == "audio_sync":
                video_url = sync_audio(
                    video_url=input_data.get("video_url"),
                    audio_url=input_data.get("audio_url"),
                )
                result = {"video_url": video_url, "type": "synced"}
                
            else:
                raise ValueError(f"Unsupported editor job type: {job_type}")
            
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

### 1. 硬體編碼

```python
def get_video_codec() -> str:
    """根據硬體選擇最佳編碼器"""
    if USE_HW_ENCODING:
        # 檢查 NVIDIA GPU 是否可用
        import subprocess
        try:
            result = subprocess.run(
                ["nvidia-smi"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return "h264_nvenc"  # NVIDIA NVENC
        except:
            pass
    return "libx264"  # 軟體編碼
```

### 2. 並行處理

```python
from concurrent.futures import ThreadPoolExecutor

def batch_compose_scenes(scene_data_list: list[dict]) -> list[str]:
    """批次合成多個場景"""
    results = []
    
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_JOBS) as executor:
        futures = {
            executor.submit(
                compose_scene_video,
                scene["video_url"],
                scene.get("bgm_url"),
                scene.get("dialogue_url"),
                scene.get("subtitle_url"),
            ): scene
            for scene in scene_data_list
        }
        
        for future in as_completed(futures):
            results.append(future.result())
    
    return results
```

### 3. 暫存空間管理

```python
def cleanup_temp_dir(max_age_hours: int = 24) -> None:
    """清理過期的暫存檔案"""
    import glob
    import os
    import time
    
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    
    for file_path in glob.glob(f"{TEMP_DIR}/*"):
        file_age = current_time - os.path.getmtime(file_path)
        if file_age > max_age_seconds:
            os.remove(file_path)
            print(f"Cleaned up: {file_path}")
```

---

## 🧪 測試清單

- [ ] Worker 註冊成功
- [ ] 心跳正常發送
- [ ] 領取 `video_composition` 作業
- [ ] 合成場景影片並上傳 MinIO
- [ ] 領取 `final_render` 作業
- [ ] 渲染整集影片並上傳 MinIO
- [ ] 領取 `subtitle_burn` 作業
- [ ] 嵌入字幕並上傳結果
- [ ] 領取 `video_concat` 作業
- [ ] 串接影片並上傳結果
- [ ] 暫存空間自動清理
- [ ] 錯誤時正確回報狀態
- [ ] 輸出影片格式正確 (MP4, H.264, AAC)

---

## 🔗 相關文件

- [WORKER_PROTOCOL.md](./WORKER_PROTOCOL.md) - API 協定規格
- [VIDEO_WORKER.md](./VIDEO_WORKER.md) - Video Worker (前置依賴)
- [AUDIO_WORKER.md](./AUDIO_WORKER.md) - Audio Worker (前置依賴)
- [ORCHESTRATOR.md](./ORCHESTRATOR.md) - 工作流程協調器

---

**版本**: 1.0.0  
**最後更新**: 2026-08-10  
**硬體**: CPU 密集型，GPU 可選
