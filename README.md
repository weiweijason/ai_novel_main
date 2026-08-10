# AI Anime Studio (Control Plane MVP)

This repository now focuses on the **non-GPU control plane**:

- FastAPI API server
- Bootstrap web UI (served by FastAPI)
- Orchestrator workflow engine
- PostgreSQL metadata
- Redis (reserved for queue/cache)
- MinIO assets

Worker services (LLM/Image/Video/Audio/Editor) are intentionally separate and can be deployed on GPU machines later.

## Architecture Scope in This Repo

Implemented here:

- Project lifecycle + workflow state transitions
- Job protocol and persistence (`workers`, `jobs`)
- LLM workflow states up to `ready_for_gpu_pipeline`
- Web UI for creating projects and starting generation

Not implemented here:

- ComfyUI/Wan/F5-TTS/Whisper/FFmpeg runtime integration
- GPU worker deployment manifests

## Quick Start

1. Copy environment file:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Start control-plane services:

   ```powershell
   docker compose up --build
   ```

3. Open:

- UI: `http://localhost:8000/ui`
- API docs: `http://localhost:8000/docs`
- MinIO console: `http://localhost:9001`

## Main Endpoints

### Project / Workflow

- `POST /projects`
- `GET /projects`
- `GET /projects/{project_id}`
- `POST /projects/{project_id}/generate`
- `GET /projects/{project_id}/jobs`

### Worker Protocol

- `POST /worker/register`
- `POST /worker/heartbeat`
- `POST /worker/jobs`
- `POST /worker/jobs/claim`
- `POST /worker/jobs/{job_id}/status`
- `GET /worker/jobs/{job_id}`

### LLM Job Shortcut

- `POST /llm/jobs`

## Current Workflow States

Project flow:

1. `draft`
2. `character_analysis_pending`
3. `story_generation_pending`
4. `script_generation_pending`
5. `scene_json_generation_pending`
6. `ready_for_gpu_pipeline`

When reaching `ready_for_gpu_pipeline`, the control plane is ready to hand off to Image/Video/Audio workers.

## Database

Auto-created on API startup and also provided via SQL:

- `migrations/001_worker_protocol.sql`
- `migrations/002_control_plane.sql`

Core tables:

- `projects`, `episodes`, `scenes`, `characters`, `assets`
- `workers`, `jobs`
