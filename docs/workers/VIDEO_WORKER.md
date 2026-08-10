# Video Worker - 開發指南 (Wan)

## 📋 概述

Video Worker 負責所有影片生成任務，使用 Wan (或類似影片生成模型) 進行場景動畫、角色動作和鏡頭運動效果生成。這是 AI 動漫工作室的動態內容生成引擎。

**硬體需求**: RTX 5080 16GB VRAM

---

## 🎯 職責

| 作業類型 | 說明 | 輸入 | 輸出 |
|---------|------|------|------|
| `scene_video` | 生成場景影片 | scene_image, scene_json | video_url, metadata |
| `character_animation` | 生成角色動畫 | character_image, motion_desc | video_url, metadata |
| `camera_motion` | 生成鏡頭運動效果 | scene_video, camera_json | video_url, metadata |
| `transition_effect` | 生成場景轉換效果 | video_1, video_2, effect_type | video_url, metadata |
| `lip_sync_video` | 生成口型同步影片 | character_image, audio | video_url, metadata |

---

## 🏗️ 系統架構

```
┌─────────────────────────────────────────────────────────────┐
│                    Video Worker Loop                         │
│                                                               │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────────┐   │
│  │ 1.Register│──►│ 2.Claim  │──►│ 3. Load Video Model   │   │
│  │  (註冊)    │    │  (領取)   │    │  (載入 Wan 模型)      │   │
│  └──────────┘    └──────────┘    └──────────┬───────────┘   │
│                                             │                │
│  ┌──────────┐    ┌──────────┐    ┌─────────▼──────────┐    │
│  │ 5.Heartbeat│◄─│ 4.Upload │◄─│ 4. Generate & Upload │    │
│  │  (心跳)    │    │  (上傳)   │    │  (生成並上傳)        │    │
│  └──────────┘    └──────────┘    └────────────────────┘    │
│                                                               │
│  VRAM 管理: 模型切換、幀率控制、解析度最佳化                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 硬體需求

| 項目 | 最低需求 | 建議配置 |
|------|---------|---------|
| **GPU** | RTX 5080 | RTX 5080 16GB |
| **VRAM** | 12GB | 16GB |
| **CPU** | 8 核心 | 16 核心 |
| **RAM** | 32GB | 64GB |
| **儲存** | 500GB SSD | 1TB NVMe SSD |
| **網路** | 100Mbps | 1Gbps |

---

## 📦 依賴套件

```txt
# requirements.txt
torch>=2.1.0
torchvision>=0.16.0
diffusers>=0.27.0
transformers>=4.37.0
accelerate>=0.26.0
decord>=0.6.0
imageio>=2.33.0
imageio-ffmpeg>=0.4.9
minio>=7.2.0
requests>=2.31.0
numpy>=1.24.0
moviepy>=1.0.3
```

**Docker 基礎映像**: `nvidia/cuda:12.4.1-devel-ubuntu22.04`

---

## 🔧 環境變數

| 變數名稱 | 說明 | 預設值 |
|---------|------|--------|
| `API_BASE_URL` | API 服務位址 | `http://api:8000` |
| `WORKER_ID` | Worker 唯一識別碼 | `video-01` |
| `WORKER_TYPE` | Worker 類型 | `video` |
| `WORKER_HOSTNAME` | Worker 主機名稱 | `video-worker` |
| `WORKER_CAPABILITIES` | 支援的作業類型 | `scene_video,character_animation,camera_motion` |
| `POLL_INTERVAL_SECONDS` | 輪詢間隔 (秒) | `5` |
| `S3_ENDPOINT` | MinIO/S3 端點 | `http://minio:9000` |
| `S3_ACCESS_KEY` | S3 存取金鑰 | `minioadmin` |
| `S3_SECRET_KEY` | S3 秘密金鑰 | `minioadmin123` |
| `S3_BUCKET` | S3 Bucket 名稱 | `assets` |
| `WAN_MODEL_PATH` | Wan 模型路徑 | `/models/wan/video_gen_model` |
| `MOTION_MODEL_PATH` | 運動模型路徑 | `/models/motion/controlnet_motion` |
| `MAX_VIDEO_LENGTH` | 最大影片長度 (秒) | `10` |
| `VIDEO_FPS` | 影片幀率 | `24` |
| `VIDEO_WIDTH` | 影片寬度 | `512` |
| `VIDEO_HEIGHT` | 影片高度 | `512` |
| `NUM_INFERENCE_STEPS` | 推理步數 | `50` |
| `GUIDANCE_SCALE` | 指導強度 | `7.5` |

---

## 📝 核心函式說明

### 1. Worker 註冊

```python
def register_worker() -> None:
    """
    向 API 註冊 Video Worker
    
    Request:
    POST /worker/register
    {
        "worker_id": "video-01",
        "worker_type": "video",
        "hostname": "video-worker",
        "capabilities": ["scene_video", "character_animation", "camera_motion"],
        "models": ["wan-video-gen-v1", "controlnet-motion"]
    }
    
    Response: 200 OK
    """
    payload = {
        "worker_id": WORKER_ID,
        "worker_type": WORKER_TYPE,
        "hostname": WORKER_HOSTNAME,
        "capabilities": WORKER_CAPABILITIES,
        "models": ["wan-video-gen-v1"],
    }
    response = requests.post(f"{API_BASE_URL}/worker/register", json=payload, timeout=10)
    response.raise_for_status()
```

### 2. 領取作業

```python
def claim_job() -> dict | None:
    """
    從佇列領取下一個影片生成作業
    
    Request:
    POST /worker/jobs/claim
    {"worker_id": "video-01"}
    
    Response:
    - 200: {"job_id": "...", "type": "scene_video", "input": {...}}
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

### 3. 場景影片生成

```python
def generate_scene_video(scene_image_url: str, scene_json: dict) -> str:
    """
    生成場景影片
    
    Args:
        scene_image_url: MinIO 上的場景圖片 URL
        scene_json: {
            "duration": 6,
            "camera": {"movement": "pan_right", "speed": "slow"},
            "characters": [
                {"id": "char_001", "motion": "walking", "direction": "left_to_right"}
            ],
            "video": {
                "prompt": "subtle movement, gentle breeze",
                "motion_strength": 0.3
            }
        }
    
    Returns:
        video_url: MinIO 上的影片 URL
    
    流程:
    1. 從 MinIO 下載場景圖片
    2. 建構影片生成 prompt
    3. 使用 Wan 模型生成影片幀
    4. 編碼為 MP4
    5. 上傳到 MinIO
    6. 回傳 URL
    """
    # 1. 下載場景圖片
    scene_image_path = download_from_s3(scene_image_url)
    
    # 2. 建構 prompt
    prompt = scene_json.get("video", {}).get("prompt", "subtle movement")
    motion_strength = scene_json.get("video", {}).get("motion_strength", 0.3)
    
    # 3. 準備 Wan 模型
    pipe = WanVideoPipeline.from_pretrained(
        WAN_MODEL_PATH,
        torch_dtype=torch.float16
    )
    pipe = pipe.to("cuda")
    
    # 4. 生成影片
    video_frames = pipe(
        prompt=prompt,
        image=scene_image_path,
        num_frames=VIDEO_FPS * scene_json.get("duration", 6),
        motion_strength=motion_strength,
        guidance_scale=GUIDANCE_SCALE,
        num_inference_steps=NUM_INFERENCE_STEPS,
    ).frames[0]
    
    # 5. 編碼為 MP4
    video_path = f"/tmp/video_{uuid4().hex}.mp4"
    save_video(video_frames, video_path, fps=VIDEO_FPS)
    
    # 6. 上傳到 MinIO
    object_name = f"videos/scenes/{scene_json['scene_id']}/{uuid4().hex}.mp4"
    video_url = upload_to_s3(video_path, object_name)
    
    # 清理
    cleanup([scene_image_path, video_path])
    torch.cuda.empty_cache()
    
    return video_url
```

### 4. 角色動畫生成

```python
def generate_character_animation(character_image_url: str, motion_desc: dict) -> str:
    """
    生成角色動畫
    
    Args:
        character_image_url: MinIO 上的角色圖片 URL
        motion_desc: {
            "motion_type": "walking",
            "direction": "left_to_right",
            "speed": "normal",
            "duration": 3
        }
    
    Returns:
        video_url: MinIO 上的角色動畫 URL
    
    流程:
    1. 下載角色圖片
    2. 使用 ControlNet 控制運動
    3. 生成動畫幀
    4. 編碼並上傳
    """
    # 1. 下載角色圖片
    character_image_path = download_from_s3(character_image_url)
    
    # 2. 準備 ControlNet + Wan 模型
    controlnet = ControlNetModel.from_pretrained(MOTION_MODEL_PATH, torch_dtype=torch.float16)
    pipe = WanVideoPipeline.from_pretrained(
        WAN_MODEL_PATH,
        controlnet=controlnet,
        torch_dtype=torch.float16
    )
    pipe = pipe.to("cuda")
    
    # 3. 生成動畫
    video_frames = pipe(
        prompt=f"character {motion_desc['motion_type']}, {motion_desc['direction']}",
        image=character_image_path,
        control_image=generate_motion_control(motion_desc),
        num_frames=VIDEO_FPS * motion_desc.get("duration", 3),
    ).frames[0]
    
    # 4. 編碼並上傳
    video_path = f"/tmp/animation_{uuid4().hex}.mp4"
    save_video(video_frames, video_path, fps=VIDEO_FPS)
    
    object_name = f"videos/animations/{uuid4().hex}.mp4"
    video_url = upload_to_s3(video_path, object_name)
    
    cleanup([character_image_path, video_path])
    torch.cuda.empty_cache()
    
    return video_url
```

### 5. 鏡頭運動效果

```python
def generate_camera_motion(video_url: str, camera_json: dict) -> str:
    """
    生成鏡頭運動效果
    
    Args:
        video_url: MinIO 上的原始影片 URL
        camera_json: {
            "movement": "pan_right",
            "speed": "slow",
            "zoom": "in",
            "zoom_speed": "medium"
        }
    
    Returns:
        video_url: MinIO 上的處理後影片 URL
    
    流程:
    1. 下載原始影片
    2. 使用 FFmpeg 或 OpenCV 應用鏡頭運動
    3. 上傳處理後影片
    """
    import cv2
    import numpy as np
    
    # 1. 下載原始影片
    video_path = download_from_s3(video_url)
    
    # 2. 讀取影片
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # 3. 應用鏡頭運動
    output_path = f"/tmp/camera_motion_{uuid4().hex}.mp4"
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    
    movement_type = camera_json.get("movement", "static")
    movement_speed = camera_json.get("speed", "slow")
    
    offset_x = 0
    offset_y = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # 根據鏡頭運動調整畫面
        if movement_type == "pan_right":
            offset_x += movement_speed_map.get(movement_speed, 1)
        elif movement_type == "pan_left":
            offset_x -= movement_speed_map.get(movement_speed, 1)
        
        # 應用偏移
        M = np.float32([[1, 0, offset_x], [0, 1, offset_y]])
        moved_frame = cv2.warpAffine(frame, M, (width, height))
        
        out.write(moved_frame)
    
    cap.release()
    out.release()
    
    # 4. 上傳
    object_name = f"videos/camera_motion/{uuid4().hex}.mp4"
    video_url = upload_to_s3(output_path, object_name)
    
    cleanup([video_path, output_path])
    
    return video_url
```

### 6. VRAM 管理

```python
def manage_vram() -> None:
    """
    VRAM 管理策略
    
    影片生成需要更多 VRAM，需要更積極的管理
    """
    import torch
    
    # 檢查可用 VRAM
    free_vram = torch.cuda.mem_get_info()[0] / 1024**3  # GB
    
    if free_vram < 6:  # 少於 6GB
        torch.cuda.empty_cache()
        free_vram = torch.cuda.mem_get_info()[0] / 1024**3
    
    if free_vram < 4:  # 少於 4GB
        # 減少解析度或幀數
        global VIDEO_WIDTH, VIDEO_HEIGHT
        VIDEO_WIDTH = 256
        VIDEO_HEIGHT = 256
        
        time.sleep(10)
```

---

## 🎬 Wan 模型使用範例

### 基本影片生成

```python
from diffusers import WanVideoPipeline
import torch

# 載入模型
pipe = WanVideoPipeline.from_pretrained(
    "wan-ai/wan2.1-t2v-1.3b",
    torch_dtype=torch.float16
)
pipe = pipe.to("cuda")

# 生成影片
video = pipe(
    prompt="anime girl walking in cherry blossom garden",
    num_frames=24 * 5,  # 5 seconds at 24fps
    height=512,
    width=512,
    guidance_scale=7.5,
    num_inference_steps=50,
)

# 儲存影片
video.save_frames("output/", fps=24)
```

### 圖片到影片

```python
from diffusers import WanVideoPipeline
from PIL import Image
import torch

# 載入模型
pipe = WanVideoPipeline.from_pretrained(
    "wan-ai/wan2.1-i2v-1.3b",
    torch_dtype=torch.float16
)
pipe = pipe.to("cuda")

# 載入圖片
image = Image.open("scene_image.png").convert("RGB")

# 生成影片
video = pipe(
    prompt="gentle breeze, leaves swaying",
    image=image,
    num_frames=24 * 6,
    motion_strength=0.3,
)

# 儲存
video.save_frames("output/", fps=24)
```

---

## 🔄 Worker 主循環

```python
def loop() -> None:
    """Video Worker 主循環"""
    print(f"[{datetime.now().isoformat()}] Video Worker starting...")
    print(f"  WORKER_ID: {WORKER_ID}")
    print(f"  WAN_MODEL_PATH: {WAN_MODEL_PATH}")
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
            
            # 執行生成
            if job_type == "scene_video":
                video_url = generate_scene_video(
                    input_data.get("scene_image_url"),
                    input_data.get("scene_json", {})
                )
                result = {"video_url": video_url, "type": "scene"}
                
            elif job_type == "character_animation":
                video_url = generate_character_animation(
                    input_data.get("character_image_url"),
                    input_data.get("motion_desc", {})
                )
                result = {"video_url": video_url, "type": "animation"}
                
            elif job_type == "camera_motion":
                video_url = generate_camera_motion(
                    input_data.get("video_url"),
                    input_data.get("camera_json", {})
                )
                result = {"video_url": video_url, "type": "camera_motion"}
                
            elif job_type == "transition_effect":
                video_url = generate_transition_effect(
                    input_data.get("video_1_url"),
                    input_data.get("video_2_url"),
                    input_data.get("effect_type", "fade")
                )
                result = {"video_url": video_url, "type": "transition"}
                
            else:
                raise ValueError(f"Unsupported video job type: {job_type}")
            
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
# 預載入 Wan 模型
WAN_PIPE = None

def get_wan_pipeline():
    global WAN_PIPE
    if WAN_PIPE is None:
        WAN_PIPE = WanVideoPipeline.from_pretrained(
            WAN_MODEL_PATH,
            torch_dtype=torch.float16
        )
        WAN_PIPE = WAN_PIPE.to("cuda")
    return WAN_PIPE
```

### 2. 解析度縮放

```python
def optimize_resolution(vram_free_gb: float) -> tuple[int, int]:
    """根據可用 VRAM 調整解析度"""
    if vram_free_gb > 10:
        return 512, 512
    elif vram_free_gb > 6:
        return 384, 384
    else:
        return 256, 256
```

### 3. 幀率控制

```python
def optimize_fps(duration: float, vram_free_gb: float) -> int:
    """根據可用 VRAM 調整幀率"""
    if vram_free_gb > 8:
        return 24  # 標準幀率
    elif vram_free_gb > 4:
        return 12  # 降低幀率
    else:
        return 8   # 最低幀率
```

---

## 🧪 測試清單

- [ ] Worker 註冊成功
- [ ] 心跳正常發送
- [ ] 領取 `scene_video` 作業
- [ ] 生成場景影片並上傳 MinIO
- [ ] 領取 `character_animation` 作業
- [ ] 生成角色動畫並上傳 MinIO
- [ ] VRAM 不足時正確處理
- [ ] 錯誤時正確回報狀態
- [ ] 影片格式正確 (MP4, H.264)

---

## 🔗 相關文件

- [WORKER_PROTOCOL.md](./WORKER_PROTOCOL.md) - API 協定規格
- [IMAGE_WORKER.md](./IMAGE_WORKER.md) - Image Worker (前置依賴)
- [ORCHESTRATOR.md](./ORCHESTRATOR.md) - 工作流程協調器

---

**版本**: 1.0.0  
**最後更新**: 2026-08-10  
**硬體**: RTX 5080 16GB
