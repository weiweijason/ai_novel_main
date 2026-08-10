# Image Worker - 開發指南 (ComfyUI)

## 📋 概述

Image Worker 負責所有影像生成任務，使用 ComfyUI + Stable Diffusion 進行角色繪圖、場景繪圖和背景生成。這是 AI 動漫工作室的視覺內容生成引擎。

**硬體需求**: RTX 5090 32GB VRAM

---

## 🎯 職責

| 作業類型 | 說明 | 輸入 | 輸出 |
|---------|------|------|------|
| `character_image` | 生成角色立繪 | character_profile, style | image_url, metadata |
| `scene_image` | 生成場景圖片 | scene_json, characters | image_url, metadata |
| `background_image` | 生成背景圖片 | location_data, time, weather | image_url, metadata |
| `character_expression` | 生成角色表情變化 | character_base_image, emotion | image_url, metadata |
| `character_pose` | 生成角色姿勢變化 | character_base_image, pose_desc | image_url, metadata |

---

## 🏗️ 系統架構

```
┌─────────────────────────────────────────────────────────────┐
│                    Image Worker Loop                         │
│                                                               │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────────┐   │
│  │ 1.Register│──►│ 2.Claim  │──►│ 3. Load ComfyUI Workflow│  │
│  │  (註冊)    │    │  (領取)   │    │  (載入工作流)          │   │
│  └──────────┘    └──────────┘    └──────────┬───────────┘   │
│                                             │                │
│  ┌──────────┐    ┌──────────┐    ┌─────────▼──────────┐    │
│  │ 5.Heartbeat│◄─│ 4.Upload │◄─│ 4. Generate & Upload │    │
│  │  (心跳)    │    │  (上傳)   │    │  (生成並上傳)        │    │
│  └──────────┘    └──────────┘    └────────────────────┘    │
│                                                               │
│  VRAM 管理: 自動清理、批次處理、模型切換、記憶體最佳化              │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 硬體需求

| 項目 | 最低需求 | 建議配置 |
|------|---------|---------|
| **GPU** | RTX 5090 | RTX 5090 32GB |
| **VRAM** | 24GB | 32GB |
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
diffusers>=0.24.0
transformers>=4.35.0
accelerate>=0.24.0
safetensors>=0.4.0
Pillow>=10.0.0
comfyui>=0.3.0
minio>=7.2.0
requests>=2.31.0
numpy>=1.24.0
```

**Docker 基礎映像**: `nvidia/cuda:12.4.1-devel-ubuntu22.04`

---

## 🔧 環境變數

| 變數名稱 | 說明 | 預設值 |
|---------|------|--------|
| `API_BASE_URL` | API 服務位址 | `http://api:8000` |
| `WORKER_ID` | Worker 唯一識別碼 | `image-01` |
| `WORKER_TYPE` | Worker 類型 | `image` |
| `WORKER_HOSTNAME` | Worker 主機名稱 | `image-worker` |
| `WORKER_CAPABILITIES` | 支援的作業類型 | `character_image,scene_image,background_image` |
| `POLL_INTERVAL_SECONDS` | 輪詢間隔 (秒) | `5` |
| `S3_ENDPOINT` | MinIO/S3 端點 | `http://minio:9000` |
| `S3_ACCESS_KEY` | S3 存取金鑰 | `minioadmin` |
| `S3_SECRET_KEY` | S3 秘密金鑰 | `minioadmin123` |
| `S3_BUCKET` | S3 Bucket 名稱 | `assets` |
| `COMFYUI_API_URL` | ComfyUI API 位址 | `http://localhost:8188` |
| `SD_MODEL_PATH` | SD 模型路徑 | `/models/checkpoints/anime_model.safetensors` |
| `VAE_PATH` | VAE 模型路徑 | `/models/vae/anime_vae.safetensors` |
| `CONTROLNET_PATH` | ControlNet 路徑 | `/models/controlnet/pose_controlnet.safetensors` |
| `MAX_BATCH_SIZE` | 最大批次大小 | `4` |
| `IMAGE_WIDTH` | 預設影像寬度 | `512` |
| `IMAGE_HEIGHT` | 預設影像高度 | `768` |
| `CFG_SCALE` | 分類指導強度 | `7.5` |
| `NUM_INFERENCE_STEPS` | 推理步數 | `30` |
| `SAMPLER` | 取樣器 | `euler_ancestral` |

---

## 📝 核心函式說明

### 1. Worker 註冊

```python
def register_worker() -> None:
    """
    向 API 註冊 Image Worker
    
    Request:
    POST /worker/register
    {
        "worker_id": "image-01",
        "worker_type": "image",
        "hostname": "image-worker",
        "capabilities": ["character_image", "scene_image", "background_image"],
        "models": ["stable-diffusion-xl-anime", "controlnet-pose"]
    }
    
    Response: 200 OK
    """
    payload = {
        "worker_id": WORKER_ID,
        "worker_type": WORKER_TYPE,
        "hostname": WORKER_HOSTNAME,
        "capabilities": WORKER_CAPABILITIES,
        "models": ["stable-diffusion-xl-anime"],
    }
    response = requests.post(f"{API_BASE_URL}/worker/register", json=payload, timeout=10)
    response.raise_for_status()
```

### 2. 領取作業

```python
def claim_job() -> dict | None:
    """
    從佇列領取下一個影像生成作業
    
    Request:
    POST /worker/jobs/claim
    {"worker_id": "image-01"}
    
    Response:
    - 200: {"job_id": "...", "type": "character_image", "input": {...}}
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

### 3. 角色圖片生成

```python
def generate_character_image(character_profile: dict) -> str:
    """
    生成角色立繪
    
    Args:
        character_profile: {
            "name": "角色名稱",
            "appearance": {
                "hair_color": "black",
                "eye_color": "blue",
                "clothing": "school uniform",
                "style": "anime"
            },
            "pose": "standing",
            "expression": "smile"
        }
    
    Returns:
        image_url: MinIO 上的圖片 URL
    
    流程:
    1. 建構 prompt 從 character_profile
    2. 準備 ComfyUI workflow JSON
    3. 發送請求到 ComfyUI API
    4. 等待生成完成
    5. 下載圖片
    6. 上傳到 MinIO
    7. 回傳 URL
    """
    # 1. 建構 prompt
    prompt = build_character_prompt(character_profile)
    
    # 2. 準備 ComfyUI workflow
    workflow = build_comfyui_workflow(
        prompt=prompt,
        negative_prompt="ugly, deformed, noisy, blurry",
        width=IMAGE_WIDTH,
        height=IMAGE_HEIGHT,
        steps=NUM_INFERENCE_STEPS,
        cfg_scale=CFG_SCALE,
        sampler=SAMPLER,
    )
    
    # 3. 發送請求到 ComfyUI
    client_id = str(uuid4())
    response = requests.post(
        f"{COMFYUI_API_URL}/prompt",
        json={"prompt": workflow, "client_id": client_id},
        timeout=30,
    )
    response.raise_for_status()
    prompt_id = response.json()["prompt_id"]
    
    # 4. 等待生成完成
    image_path = wait_for_comfyui_completion(prompt_id, client_id)
    
    # 5. 上傳到 MinIO
    object_name = f"characters/{character_profile['name']}/{uuid4().hex}.png"
    image_url = upload_to_s3(image_path, object_name)
    
    return image_url
```

### 4. 場景圖片生成

```python
def generate_scene_image(scene_json: dict, character_images: dict) -> str:
    """
    生成場景圖片
    
    Args:
        scene_json: {
            "location": {"id": "classroom", "time": "afternoon", "weather": "clear"},
            "characters": [{"id": "char_001", "pose": "standing", "expression": "happy"}],
            "camera": {"shot": "medium", "angle": "eye_level"}
        }
        character_images: {"char_001": "minio_url_to_character.png"}
    
    Returns:
        image_url: MinIO 上的場景圖片 URL
    
    流程:
    1. 從 scene_json 建構場景 prompt
    2. 使用 ControlNet 控制角色姿勢
    3. 使用 IP-Adapter 保持角色一致性
    4. 生成場景圖片
    5. 上傳到 MinIO
    """
    # 1. 建構場景 prompt
    prompt = build_scene_prompt(scene_json)
    
    # 2. 準備 ComfyUI workflow (使用 ControlNet + IP-Adapter)
    workflow = build_scene_workflow(
        prompt=prompt,
        character_images=character_images,
        controlnet_path=CONTROLNET_PATH,
        ip_adapter_strength=0.7,
    )
    
    # 3-5. 生成並上傳
    client_id = str(uuid4())
    response = requests.post(f"{COMFYUI_API_URL}/prompt", json={"prompt": workflow, "client_id": client_id})
    prompt_id = response.json()["prompt_id"]
    image_path = wait_for_comfyui_completion(prompt_id, client_id)
    
    object_name = f"scenes/{scene_json['scene_id']}/{uuid4().hex}.png"
    return upload_to_s3(image_path, object_name)
```

### 5. VRAM 管理

```python
def manage_vram() -> None:
    """
    VRAM 管理策略
    
    1. 生成前檢查可用 VRAM
    2. 如果 VRAM 不足，清理快取
    3. 如果仍不足，減少批次大小
    4. 如果仍不足，等待其他 Worker 完成
    """
    import torch
    
    # 檢查可用 VRAM
    free_vram = torch.cuda.mem_get_info()[0] / 1024**3  # GB
    
    if free_vram < 4:  # 少於 4GB
        torch.cuda.empty_cache()
        free_vram = torch.cuda.mem_get_info()[0] / 1024**3
    
    if free_vram < 2:  # 少於 2GB
        # 等待或跳過
        time.sleep(10)
```

---

## 🎨 ComfyUI 工作流範例

### 角色生成工作流

```json
{
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 8566257,
            "steps": 30,
            "cfg": 7.5,
            "sampler_name": "euler_ancestral",
            "scheduler": "normal",
            "denoise": 1.0,
            "model": ["4", 0],
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["5", 0]
        }
    },
    "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {
            "ckpt_name": "anime_model.safetensors"
        }
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {
            "width": 512,
            "height": 768,
            "batch_size": 1
        }
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "1girl, anime style, black hair, blue eyes, school uniform, standing, smile",
            "clip": ["4", 1]
        }
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "ugly, deformed, noisy, blurry, low quality",
            "clip": ["4", 1]
        }
    },
    "8": {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["3", 0],
            "vae": ["4", 2]
        }
    },
    "9": {
        "class_type": "SaveImage",
        "inputs": {
            "images": ["8", 0],
            "filename_prefix": "character"
        }
    }
}
```

---

## 🔄 Worker 主循環

```python
def loop() -> None:
    """Image Worker 主循環"""
    print(f"[{datetime.now().isoformat()}] Image Worker starting...")
    print(f"  WORKER_ID: {WORKER_ID}")
    print(f"  COMFYUI_API_URL: {COMFYUI_API_URL}")
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
            if job_type == "character_image":
                image_url = generate_character_image(input_data)
                result = {"image_url": image_url, "type": "character"}
                
            elif job_type == "scene_image":
                image_url = generate_scene_image(input_data.get("scene_json"), input_data.get("character_images", {}))
                result = {"image_url": image_url, "type": "scene"}
                
            elif job_type == "background_image":
                image_url = generate_background_image(input_data)
                result = {"image_url": image_url, "type": "background"}
                
            else:
                raise ValueError(f"Unsupported image job type: {job_type}")
            
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
# 預載入常用模型
MODEL_CACHE = {}

def get_model(model_path: str):
    if model_path not in MODEL_CACHE:
        MODEL_CACHE[model_path] = load_model(model_path)
    return MODEL_CACHE[model_path]
```

### 2. 批次處理

```python
def generate_batch(character_profiles: list[dict]) -> list[str]:
    """批次生成角色圖片"""
    prompts = [build_character_prompt(p) for p in character_profiles]
    
    # ComfyUI 批次處理
    workflow = build_batch_workflow(prompts, batch_size=MAX_BATCH_SIZE)
    
    # 生成並上傳
    image_paths = generate_from_workflow(workflow)
    urls = [upload_to_s3(path, f"characters/{p['name']}/{uuid4().hex}.png") 
            for path, p in zip(image_paths, character_profiles)]
    
    return urls
```

### 3. 記憶體最佳化

```python
import torch

# 使用 CPU 離載
pipe.enable_model_cpu_offload()

# 使用 xFormers
pipe.enable_xformers_memory_efficient_attention()

# 使用 8-bit 優化
pipe.enable_sequential_cpu_offload()
```

---

## 🧪 測試清單

- [ ] Worker 註冊成功
- [ ] 心跳正常發送
- [ ] 領取 `character_image` 作業
- [ ] 生成角色圖片並上傳 MinIO
- [ ] 領取 `scene_image` 作業
- [ ] 生成場景圖片並上傳 MinIO
- [ ] VRAM 不足時正確處理
- [ ] 錯誤時正確回報狀態
- [ ] ComfyUI 斷線時重連

---

## 🔗 相關文件

- [WORKER_PROTOCOL.md](./WORKER_PROTOCOL.md) - API 協定規格
- [GPU_WORKER.md](./GPU_WORKER.md) - GPU Worker 總覽
- [ORCHESTRATOR.md](./ORCHESTRATOR.md) - 工作流程協調器

---

**版本**: 1.0.0  
**最後更新**: 2026-08-10  
**硬體**: RTX 5090 32GB
