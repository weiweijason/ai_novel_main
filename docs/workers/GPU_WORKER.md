# GPU Worker - 開發指南

## 📋 概述

GPU Worker 負責所有影像和影片渲染任務，包括角色繪圖、場景繪圖、背景生成和影片動畫生成。這是 AI 動漫工作室的視覺內容生成引擎。

## 🎯 職責

| 作業類型 | 說明 | 輸入 | 輸出 |
|---------|------|------|------|
| `character_image_gen` | 生成角色立繪 | character_profile, style | image_url, metadata |
| `scene_image_gen` | 生成場景圖片 | scene_json | image_url, metadata |
| `background_gen` | 生成背景圖片 | location_data | image_url, metadata |
| `video_gen` | 生成場景影片 | scene_json, images | video_url, metadata |
| `lip_sync_gen` | 生成口型同步影片 | character_image, audio | video_url, metadata |

## 🏗️ 系統架構

```
┌─────────────────────────────────────────────────────┐
│                  GPU Worker Loop                     │
│                                                      │
│  ┌──────────┐    ┌──────────┐    ┌──────────────┐   │
│  │ 1. Register│──►│ 2. Claim  │──►│ 3. Execute   │   │
│  │  (註冊)    │    │  (領取)   │    │  (GPU 渲染)  │   │
│  └──────────┘    └──────────┘    └──────┬───────┘   │
│                                         │            │
│  ┌──────────┐    ┌──────────┐    ┌──────▼───────┐   │
│  │ 5. Heartbeat│◄─│ 4. Upload │◄─│ 4. Upload    │   │
│  │  (心跳)    │    │  (上傳)   │    │  (結果上傳)  │   │
│  └──────────┘    └──────────┘    └──────────────┘   │
│                                                      │
│  VRAM 管理: 自動清理、批次處理、記憶體最佳化             │
└─────────────────────────────────────────────────────┘
```

## 🔧 環境變數

| 變數名稱 | 說明 | 預設值 |
|---------|------|--------|
| `API_BASE_URL` | API 服務位址 | `http://localhost:8000` |
| `WORKER_ID` | Worker 唯一識別碼 | `gpu-01` |
| `WORKER_TYPE` | Worker 類型 | `gpu` |
| `WORKER_HOSTNAME` | Worker 主機名稱 | `gpu-worker` |
| `WORKER_CAPABILITIES` | 支援的作業類型 | `character_image_gen,scene_image_gen,video_gen` |
| `POLL_INTERVAL_SECONDS` | 輪詢間隔 (秒) | `5` |
| `S3_ENDPOINT` | MinIO/S3 端點 | `http://minio:9000` |
| `S3_ACCESS_KEY` | S3 存取金鑰 | `minioadmin` |
| `S3_SECRET_KEY` | S3 秘密金鑰 | `minioadmin123` |
| `STABLE_DIFFUSION_MODEL` | SD 模型路徑 | `runwayml/stable-diffusion-v1-5` |
| `VIDEO_MODEL` | 影片生成模型 | `damo-vilab/text-to-video-ms-1.7b` |
| `GPU_DEVICE` | GPU 裝置編號 | `0` |
| `MAX_BATCH_SIZE` | 最大批次大小 | `4` |
| `IMAGE_WIDTH` | 預設圖片寬度 | `512` |
| `IMAGE_HEIGHT` | 預設圖片高度 | `512` |
| `VIDEO_FRAMES` | 預設影片幀數 | `16` |

## 🖥️ 硬體需求

### 最低需求
- **GPU**: NVIDIA RTX 3060 (12GB VRAM)
- **RAM**: 16GB
- **Storage**: 100GB SSD

### 推薦配置
- **GPU**: NVIDIA RTX 4090 (24GB VRAM) 或 A100 (40GB VRAM)
- **RAM**: 32GB
- **Storage**: 500GB NVMe SSD

### 企業級配置
- **GPU**: 多張 A100/H100 (80GB VRAM)
- **RAM**: 128GB
- **Storage**: 2TB NVMe SSD RAID

## 📦 依賴套件

```txt
torch>=2.0.0
torchvision>=0.15.0
diffusers>=0.24.0
transformers>=4.35.0
accelerate>=0.24.0
bitsandbytes>=0.41.0  # 對於 8-bit 量化
xformers>=0.0.20      # 記憶體最佳化
minio>=7.2.0
pillow>=10.0.0
opencv-python>=4.8.0
imageio>=2.31.0
imageio-ffmpeg>=0.4.0
```

## 📝 核心函式說明

### 1. GPU 資源管理

```python
import torch

class GPUManager:
    """GPU 資源管理器"""
    
    def __init__(self, device_id: int = 0):
        self.device = torch.device(f"cuda:{device_id}" if torch.cuda.is_available() else "cpu")
        self.vram_total = torch.cuda.get_device_properties(self.device).total_memory
        self.vram_used = 0
        self.current_batch = []
        
    def get_available_vram(self) -> int:
        """取得可用 VRAM (MB)"""
        free, total = torch.cuda.mem_get_info(self.device)
        return free // (1024 * 1024)  # 轉換為 MB
    
    def clear_cache(self) -> None:
        """清理 GPU 快取"""
        torch.cuda.empty_cache()
        self.vram_used = 0
        
    def can_fit_batch(self, batch_size: int, model_vram_requirement: int) -> bool:
        """檢查批次是否能放入 VRAM"""
        available = self.get_available_vram()
        required = model_vram_requirement * batch_size
        return available > required
```

### 2. 角色圖片生成

```python
from diffusers import StableDiffusionPipeline
import torch

def generate_character_image(character_profile: dict, style: str = "anime") -> dict:
    """
    生成角色立繪
    
    Input:
    {
        "name": "艾莉亞",
        "appearance": {
            "hair": "長銀髮",
            "eyes": "藍色",
            "clothing": "輕甲鎧",
            "accessories": ["佩劍"]
        },
        "personality": { ... }
    }
    
    Output:
    {
        "image_url": "http://minio:9000/assets/characters/char_001.png",
        "metadata": {
            "width": 512,
            "height": 768,
            "seed": 12345,
            "steps": 50,
            "cfg_scale": 7.5
        }
    }
    """
    
    # 建構 prompt
    prompt = build_character_prompt(character_profile, style)
    negative_prompt = "low quality, blurry, distorted, ugly, deformed"
    
    # 載入模型
    pipe = StableDiffusionPipeline.from_pretrained(
        os.getenv("STABLE_DIFFUSION_MODEL", "runwayml/stable-diffusion-v1-5"),
        torch_dtype=torch.float16
    ).to("cuda")
    
    # 生成圖片
    image = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        num_inference_steps=50,
        guidance_scale=7.5,
        width=512,
        height=768
    ).images[0]
    
    # 上傳到 MinIO
    image_bytes = image.tobytes()
    storage_key = f"characters/{character_profile['name']}_portrait.png"
    upload_to_minio(image_bytes, storage_key, "image/png")
    
    return {
        "image_url": f"{os.getenv('S3_ENDPOINT')}/assets/{storage_key}",
        "metadata": {
            "width": image.width,
            "height": image.height,
            "seed": pipe.generator.initial_seed if hasattr(pipe, 'generator') else None,
            "steps": 50,
            "cfg_scale": 7.5
        }
    }


def build_character_prompt(character: dict, style: str) -> str:
    """建構角色生成 prompt"""
    
    appearance = character.get("appearance", {})
    personality = character.get("personality", {})
    
    base_prompt = f"1girl, anime style, {style} art"
    
    # 外觀描述
    if appearance.get("hair"):
        base_prompt += f", {appearance['hair']}"
    if appearance.get("eyes"):
        base_prompt += f", {appearance['eyes']} eyes"
    if appearance.get("clothing"):
        base_prompt += f", wearing {appearance['clothing']}"
    if appearance.get("accessories"):
        base_prompt += ", " + ", ".join(appearance["accessories"])
    
    # 性格特質轉為表情
    traits = personality.get("traits", [])
    if "勇敢" in traits or "determined" in traits:
        base_prompt += ", determined expression"
    if "溫柔" in traits or "kind" in traits:
        base_prompt += ", gentle smile"
    
    # 品質提升
    base_prompt += ", masterpiece, best quality, detailed, sharp focus"
    
    return base_prompt
```

### 3. 場景圖片生成

```python
def generate_scene_image(scene_json: dict) -> dict:
    """
    生成場景圖片
    
    Input: scene_json (從 LLM Worker 生成的場景結構)
    
    Output:
    {
        "image_url": "http://minio:9000/assets/scenes/scene_001.png",
        "metadata": { ... }
    }
    """
    
    visual = scene_json.get("visual", {})
    prompt = visual.get("prompt", "anime scene")
    negative_prompt = visual.get("negative_prompt", "low quality")
    
    # 載入模型
    pipe = StableDiffusionPipeline.from_pretrained(
        os.getenv("STABLE_DIFFUSION_MODEL"),
        torch_dtype=torch.float16
    ).to("cuda")
    
    # 生成圖片
    image = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        num_inference_steps=50,
        guidance_scale=7.5,
        width=1024,
        height=576  # 16:9 比例
    ).images[0]
    
    # 上傳
    storage_key = f"scenes/{scene_json['scene_id']}.png"
    upload_to_minio(image.tobytes(), storage_key, "image/png")
    
    return {
        "image_url": f"{os.getenv('S3_ENDPOINT')}/assets/{storage_key}",
        "metadata": {
            "width": image.width,
            "height": image.height,
            "steps": 50
        }
    }
```

### 4. 影片生成

```python
from diffusers import TextToVideoSDPipeline

def generate_video(scene_json: dict, image_url: str) -> dict:
    """
    生成場景影片
    
    Input:
    - scene_json: 場景結構
    - image_url: 參考圖片 URL
    
    Output:
    {
        "video_url": "http://minio:9000/assets/videos/scene_001.mp4",
        "metadata": {
            "frames": 16,
            "fps": 8,
            "duration": 2.0
        }
    }
    """
    
    video_config = scene_json.get("video", {})
    prompt = video_config.get("prompt", "subtle movement")
    motion_strength = video_config.get("motion_strength", 0.3)
    
    # 載入影片生成模型
    pipe = TextToVideoSDPipeline.from_pretrained(
        os.getenv("VIDEO_MODEL", "damo-vilab/text-to-video-ms-1.7b"),
        torch_dtype=torch.float16
    ).to("cuda")
    
    # 生成影片
    video_frames = pipe(
        prompt=prompt,
        num_inference_steps=50,
        num_frames=16,
        guidance_scale=9.0
    ).frames[0]
    
    # 編碼為 MP4
    import imageio
    import numpy as np
    
    frames_list = [frames for frames in video_frames]
    output_path = f"/tmp/{scene_json['scene_id']}.mp4"
    
    imageio.mimwrite(
        output_path,
        frames_list,
        fps=8,
        codec="libx264"
    )
    
    # 上傳
    with open(output_path, "rb") as f:
        video_bytes = f.read()
    
    storage_key = f"videos/{scene_json['scene_id']}.mp4"
    upload_to_minio(video_bytes, storage_key, "video/mp4")
    
    return {
        "video_url": f"{os.getenv('S3_ENDPOINT')}/assets/{storage_key}",
        "metadata": {
            "frames": 16,
            "fps": 8,
            "duration": 2.0
        }
    }
```

### 5. MinIO 上傳

```python
from minio import Minio
from minio.error import S3Error
import io

def get_minio_client() -> Minio:
    """取得 MinIO 客戶端"""
    endpoint = os.getenv("S3_ENDPOINT", "http://minio:9000").replace("http://", "").replace("https://", "")
    if ":" not in endpoint:
        endpoint = f"{endpoint}:9000"
    
    return Minio(
        endpoint,
        access_key=os.getenv("S3_ACCESS_KEY", "minioadmin"),
        secret_key=os.getenv("S3_SECRET_KEY", "minioadmin123"),
        secure=False
    )


def upload_to_minio(data: bytes, key: str, content_type: str) -> str:
    """上傳檔案到 MinIO"""
    client = get_minio_client()
    
    # 確保 bucket 存在
    if not client.bucket_exists("assets"):
        client.make_bucket("assets")
    
    # 上傳
    client.put_object(
        "assets",
        key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type
    )
    
    return key
```

## 🚀 開發步驟

### 1. 設定 GPU 環境

```bash
# 安裝 NVIDIA 驅動
# 參考: https://www.nvidia.com/drivers

# 安裝 CUDA
wget https://developer.download.nvidia.com/compute/cuda/12.1.0/local_installers/cuda_12.1.0_530.30.02_linux.run
sudo sh cuda_12.1.0_530.30.02_linux.run

# 驗證 GPU
nvidia-smi
```

### 2. 安裝 Python 依賴

```bash
# 建立虛擬環境
python -m venv venv
source venv/bin/activate

# 安裝 PyTorch (CUDA 12.1)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# 安裝 Diffusers
pip install diffusers transformers accelerate

# 安裝其他依賴
pip install minio pillow opencv-python imageio imageio-ffmpeg
```

### 3. 實作 Worker 主迴圈

```python
import time
import torch

def main():
    gpu_manager = GPUManager(device_id=int(os.getenv("GPU_DEVICE", "0")))
    register_worker()
    send_heartbeat("idle", None, gpu_manager.get_gpu_info())
    
    current_job = None
    
    while True:
        try:
            if current_job is None:
                job = claim_job()
                if job:
                    current_job = job
                    send_heartbeat("busy", job["id"], gpu_manager.get_gpu_info())
                    update_job_status(job["id"], "running", progress=0.0)
            
            if current_job:
                # 執行 GPU 任務
                job_type = current_job["type"]
                payload = current_job["input"]
                
                if job_type == "character_image_gen":
                    result = generate_character_image(payload)
                elif job_type == "scene_image_gen":
                    result = generate_scene_image(payload)
                elif job_type == "video_gen":
                    result = generate_video(payload)
                else:
                    raise ValueError(f"Unknown job type: {job_type}")
                
                # 回報完成
                update_job_status(
                    current_job["id"],
                    "completed",
                    progress=1.0,
                    result=result
                )
                
                # 清理 GPU 記憶體
                gpu_manager.clear_cache()
                current_job = None
                send_heartbeat("idle", None, gpu_manager.get_gpu_info())
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

### 4. Docker 部署

```dockerfile
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

WORKDIR /app

# 安裝 Python
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# 安裝依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製程式碼
COPY . .

# 設定環境變數
ENV PYTHONUNBUFFERED=1
ENV CUDA_VISIBLE_DEVICES=0

# 啟動
CMD ["python", "main.py"]
```

## 🧪 測試清單

- [ ] GPU 裝置正確偵測
- [ ] VRAM 監控正常運作
- [ ] 角色圖片生成成功
- [ ] 場景圖片生成成功
- [ ] 影片生成成功
- [ ] 檔案正確上傳到 MinIO
- [ ] 批次處理正常
- [ ] 記憶體清理機制正常
- [ ] 錯誤處理與重試機制正常

## 🔍 效能最佳化

### VRAM 最佳化技巧

```python
# 1. 使用 8-bit 量化
from bitsandbytes import quantize_4bit

pipe = StableDiffusionPipeline.from_pretrained(
    model_name,
    load_in_4bit=True  # 4-bit 量化
)

# 2. 使用 xFormers
pipe.enable_xformers_memory_efficient_attention()

# 3. 使用 CPU 離載
pipe.enable_model_cpu_offload()

# 4. 批次處理
images = pipe(
    prompt=prompts,  # 多個 prompt
    batch_size=4
).images
```

### 生成速度參考

| 任務 | 解析度 | RTX 4090 | A100 |
|------|--------|----------|------|
| 角色圖片 | 512x768 | ~5s | ~3s |
| 場景圖片 | 1024x576 | ~8s | ~5s |
| 影片 (16幀) | 512x512 | ~30s | ~15s |

## 📚 相關文件

- [Worker 架構總覽](./ARCHITECTURE.md)
- [LLM Worker 開發指南](./LLM_WORKER.md)
- [Worker 通訊協定](./WORKER_PROTOCOL.md)

---

**版本**: 1.0.0  
**最後更新**: 2026-08-10
