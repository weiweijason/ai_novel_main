from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class WorkerRegisterRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=100)
    worker_type: str = Field(min_length=1, max_length=50)
    hostname: Optional[str] = None
    endpoint: Optional[str] = None
    gpu: Optional[str] = None
    vram: Optional[int] = None
    capabilities: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)


class WorkerRegisterResponse(BaseModel):
    worker_id: str
    status: str


class WorkerHeartbeatRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=100)
    status: str = Field(default="idle", min_length=1, max_length=50)
    current_job: Optional[str] = None
    gpu: dict[str, Any] = Field(default_factory=dict)


class WorkerHeartbeatResponse(BaseModel):
    worker_id: str
    status: str
    current_job: Optional[str]
    last_heartbeat: datetime


class WorkerJobRequest(BaseModel):
    job_id: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=100)
    project_id: Optional[str] = None
    episode_id: Optional[str] = None
    scene_id: Optional[str] = None
    worker_id: Optional[str] = None
    worker_type: Optional[str] = None
    priority: int = 5
    max_attempts: int = 3
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)


class WorkerJobAcceptedResponse(BaseModel):
    job_id: str
    status: str


class WorkerJobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: Optional[float] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class LLMJobCreateRequest(BaseModel):
    job_id: str = Field(min_length=1, max_length=100)
    job_type: Literal[
        "character_analysis",
        "story_generation",
        "script_generation",
        "scene_json_generation",
    ]
    project_id: Optional[str] = None
    episode_id: Optional[str] = None
    scene_id: Optional[str] = None
    priority: int = 5
    max_attempts: int = 3
    input: dict[str, Any] = Field(default_factory=dict)


class WorkerJobClaimRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=100)


class WorkerJobClaimResponse(BaseModel):
    job_id: str
    type: str
    project_id: Optional[str] = None
    episode_id: Optional[str] = None
    scene_id: Optional[str] = None
    input: dict[str, Any] = Field(default_factory=dict)


class WorkerJobUpdateRequest(BaseModel):
    status: Literal["running", "completed", "failed"]
    progress: Optional[float] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    source_prompt: Optional[str] = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    status: str
    source_prompt: Optional[str]


class ProjectGenerateRequest(BaseModel):
    scene_count: int = Field(default=5, ge=1, le=20)
    character_brief: str = Field(min_length=1)


class ProjectGenerateResponse(BaseModel):
    project_id: str
    status: str
    episode_id: str
    scene_count: int


class JobSummaryResponse(BaseModel):
    id: str
    job_type: str
    worker_type: Optional[str]
    status: str
    attempt: int
    max_attempts: int
    created_at: datetime
