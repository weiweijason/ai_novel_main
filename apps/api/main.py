from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import Base, engine, get_db
from models import Episode, Job, Project, Scene, Worker
from schemas import (
    JobSummaryResponse,
    LLMJobCreateRequest,
    ProjectCreateRequest,
    ProjectGenerateRequest,
    ProjectGenerateResponse,
    ProjectResponse,
    WorkerHeartbeatRequest,
    WorkerHeartbeatResponse,
    WorkerJobAcceptedResponse,
    WorkerJobClaimRequest,
    WorkerJobClaimResponse,
    WorkerJobRequest,
    WorkerJobStatusResponse,
    WorkerJobUpdateRequest,
    WorkerRegisterRequest,
    WorkerRegisterResponse,
)

app = FastAPI(title="AI Anime Studio API", version="0.3.0")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _create_job(
    db: Session,
    job_id: str,
    job_type: str,
    project_id: str | None,
    episode_id: str | None,
    scene_id: str | None,
    worker_id: str | None,
    worker_type: str | None,
    priority: int,
    max_attempts: int,
    payload: dict,
) -> Job:
    existing = db.get(Job, job_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Job already exists")

    if worker_id is not None and db.get(Worker, worker_id) is None:
        raise HTTPException(status_code=400, detail="worker_id is not registered")

    job = Job(
        id=job_id,
        project_id=project_id,
        episode_id=episode_id,
        scene_id=scene_id,
        worker_id=worker_id,
        worker_type=worker_type,
        job_type=job_type,
        status="queued",
        priority=priority,
        max_attempts=max_attempts,
        payload=payload,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _project_or_404(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "api"}


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/ui", status_code=302)


@app.get("/projects", response_model=list[ProjectResponse])
def list_projects(db: Session = Depends(get_db)) -> list[ProjectResponse]:
    projects = db.scalars(select(Project).order_by(Project.created_at.desc())).all()
    return [
        ProjectResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            status=p.status,
            source_prompt=p.source_prompt,
        )
        for p in projects
    ]


@app.post("/projects", response_model=ProjectResponse)
def create_project(payload: ProjectCreateRequest, db: Session = Depends(get_db)) -> ProjectResponse:
    project = Project(
        id=_new_id("project"),
        name=payload.name,
        description=payload.description,
        source_prompt=payload.source_prompt,
        status="draft",
        workflow_data={},
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        status=project.status,
        source_prompt=project.source_prompt,
    )


@app.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)) -> ProjectResponse:
    project = _project_or_404(db, project_id)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        status=project.status,
        source_prompt=project.source_prompt,
    )


@app.post("/projects/{project_id}/generate", response_model=ProjectGenerateResponse)
def generate_project(
    project_id: str, payload: ProjectGenerateRequest, db: Session = Depends(get_db)
) -> ProjectGenerateResponse:
    project = _project_or_404(db, project_id)
    if project.status not in ("draft", "failed"):
        raise HTTPException(status_code=409, detail="Project is already in generation flow")

    episode = Episode(
        id=_new_id("episode"),
        project_id=project.id,
        episode_number=1,
        title=f"{project.name} - Episode 1",
        status="llm_pending",
    )
    db.add(episode)

    for scene_number in range(1, payload.scene_count + 1):
        db.add(
            Scene(
                id=_new_id("scene"),
                episode_id=episode.id,
                scene_number=scene_number,
                status="llm_pending",
                scene_data={"seed_prompt": f"Scene {scene_number} of {project.name}"},
            )
        )

    project.workflow_data = {
        "episode_id": episode.id,
        "scene_count": payload.scene_count,
        "character_brief": payload.character_brief,
    }
    project.status = "character_analysis_pending"
    project.updated_at = _now()
    db.commit()

    _create_job(
        db=db,
        job_id=_new_id("job"),
        job_type="character_analysis",
        project_id=project.id,
        episode_id=episode.id,
        scene_id=None,
        worker_id=None,
        worker_type="llm",
        priority=1,
        max_attempts=3,
        payload={"input": {"brief": payload.character_brief, "project_name": project.name}},
    )

    return ProjectGenerateResponse(
        project_id=project.id,
        status=project.status,
        episode_id=episode.id,
        scene_count=payload.scene_count,
    )


@app.get("/projects/{project_id}/jobs", response_model=list[JobSummaryResponse])
def list_project_jobs(project_id: str, db: Session = Depends(get_db)) -> list[JobSummaryResponse]:
    _project_or_404(db, project_id)
    jobs = db.scalars(
        select(Job).where(Job.project_id == project_id).order_by(Job.created_at.desc())
    ).all()
    return [
        JobSummaryResponse(
            id=job.id,
            job_type=job.job_type,
            worker_type=job.worker_type,
            status=job.status,
            attempt=job.attempt,
            max_attempts=job.max_attempts,
            created_at=job.created_at,
        )
        for job in jobs
    ]


@app.get("/ui")
def ui_index(request: Request, db: Session = Depends(get_db)):
    projects = db.scalars(select(Project).order_by(Project.created_at.desc())).all()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"projects": projects},
    )


@app.get("/ui/projects/{project_id}")
def ui_project_detail(project_id: str, request: Request, db: Session = Depends(get_db)):
    project = _project_or_404(db, project_id)
    episode = db.scalar(
        select(Episode).where(Episode.project_id == project.id).order_by(Episode.created_at.desc())
    )
    scenes = []
    if episode is not None:
        scenes = db.scalars(
            select(Scene).where(Scene.episode_id == episode.id).order_by(Scene.scene_number.asc())
        ).all()
    jobs = db.scalars(
        select(Job).where(Job.project_id == project.id).order_by(Job.created_at.desc())
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="project_detail.html",
        context={"project": project, "episode": episode, "scenes": scenes, "jobs": jobs},
    )


@app.post("/ui/projects")
def ui_create_project(
    name: str = Form(...),
    description: str = Form(""),
    source_prompt: str = Form(""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    project = Project(
        id=_new_id("project"),
        name=name,
        description=description or None,
        source_prompt=source_prompt or None,
        status="draft",
        workflow_data={},
    )
    db.add(project)
    db.commit()
    return RedirectResponse(url=f"/ui/projects/{project.id}", status_code=303)


@app.post("/ui/projects/{project_id}/generate")
def ui_generate_project(
    project_id: str,
    scene_count: int = Form(5),
    character_brief: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    generate_project(
        project_id=project_id,
        payload=ProjectGenerateRequest(
            scene_count=scene_count,
            character_brief=character_brief,
        ),
        db=db,
    )
    return RedirectResponse(url=f"/ui/projects/{project_id}", status_code=303)


@app.post("/worker/register", response_model=WorkerRegisterResponse)
def register_worker(
    payload: WorkerRegisterRequest, db: Session = Depends(get_db)
) -> WorkerRegisterResponse:
    worker = db.get(Worker, payload.worker_id)
    if worker is None:
        worker = Worker(
            id=payload.worker_id,
            worker_type=payload.worker_type,
            created_at=_now(),
        )
        db.add(worker)

    worker.worker_type = payload.worker_type
    worker.hostname = payload.hostname
    worker.endpoint = payload.endpoint
    worker.gpu = payload.gpu
    worker.vram = payload.vram
    worker.capabilities = payload.capabilities
    worker.models = payload.models
    worker.status = "idle"
    worker.last_heartbeat = _now()
    db.commit()
    return WorkerRegisterResponse(worker_id=worker.id, status="registered")


@app.post("/worker/heartbeat", response_model=WorkerHeartbeatResponse)
def worker_heartbeat(
    payload: WorkerHeartbeatRequest, db: Session = Depends(get_db)
) -> WorkerHeartbeatResponse:
    worker = db.get(Worker, payload.worker_id)
    if worker is None:
        raise HTTPException(status_code=404, detail="Worker not registered")

    worker.status = payload.status
    worker.current_job = payload.current_job
    worker.gpu_info = payload.gpu
    worker.last_heartbeat = _now()
    db.commit()
    db.refresh(worker)
    return WorkerHeartbeatResponse(
        worker_id=worker.id,
        status=worker.status,
        current_job=worker.current_job,
        last_heartbeat=worker.last_heartbeat,
    )


@app.post("/worker/jobs", response_model=WorkerJobAcceptedResponse)
def create_worker_job(
    payload: WorkerJobRequest, db: Session = Depends(get_db)
) -> WorkerJobAcceptedResponse:
    job = _create_job(
        db=db,
        job_id=payload.job_id,
        job_type=payload.type,
        project_id=payload.project_id,
        episode_id=payload.episode_id,
        scene_id=payload.scene_id,
        worker_id=payload.worker_id,
        worker_type=payload.worker_type,
        priority=payload.priority,
        max_attempts=payload.max_attempts,
        payload={"input": payload.input, "output": payload.output},
    )
    return WorkerJobAcceptedResponse(job_id=job.id, status="accepted")


@app.post("/llm/jobs", response_model=WorkerJobAcceptedResponse)
def create_llm_job(
    payload: LLMJobCreateRequest, db: Session = Depends(get_db)
) -> WorkerJobAcceptedResponse:
    job = _create_job(
        db=db,
        job_id=payload.job_id,
        job_type=payload.job_type,
        project_id=payload.project_id,
        episode_id=payload.episode_id,
        scene_id=payload.scene_id,
        worker_id=None,
        worker_type="llm",
        priority=payload.priority,
        max_attempts=payload.max_attempts,
        payload={"input": payload.input},
    )
    return WorkerJobAcceptedResponse(job_id=job.id, status="accepted")


@app.post("/worker/jobs/claim", response_model=WorkerJobClaimResponse)
def claim_worker_job(
    payload: WorkerJobClaimRequest, db: Session = Depends(get_db)
) -> WorkerJobClaimResponse:
    worker = db.get(Worker, payload.worker_id)
    if worker is None:
        raise HTTPException(status_code=404, detail="Worker not registered")

    job = db.scalar(
        select(Job)
        .where(Job.status == "queued", Job.worker_type == worker.worker_type)
        .order_by(Job.priority.asc(), Job.created_at.asc())
        .limit(1)
    )
    if job is None:
        raise HTTPException(status_code=404, detail="No queued job for this worker type")

    job.worker_id = worker.id
    job.status = "running"
    job.started_at = _now()
    job.attempt = job.attempt + 1
    worker.status = "busy"
    worker.current_job = job.id
    worker.last_heartbeat = _now()
    db.commit()
    db.refresh(job)
    return WorkerJobClaimResponse(
        job_id=job.id,
        type=job.job_type,
        project_id=job.project_id,
        episode_id=job.episode_id,
        scene_id=job.scene_id,
        input=job.payload.get("input", {}),
    )


@app.post("/worker/jobs/{job_id}/status", response_model=WorkerJobStatusResponse)
def update_worker_job_status(
    job_id: str, payload: WorkerJobUpdateRequest, db: Session = Depends(get_db)
) -> WorkerJobStatusResponse:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if payload.progress is not None:
        job.progress = payload.progress
    if payload.result is not None:
        job.result = payload.result
    if payload.error is not None:
        job.error = payload.error

    job.status = payload.status
    if payload.status == "completed":
        job.completed_at = _now()
        job.progress = 1.0
    if payload.status == "failed":
        job.completed_at = _now()

    if job.worker_id is not None:
        worker = db.get(Worker, job.worker_id)
        if worker is not None:
            if payload.status in ("completed", "failed"):
                worker.status = "idle"
                worker.current_job = None
            worker.last_heartbeat = _now()

    db.commit()
    db.refresh(job)
    return WorkerJobStatusResponse(
        job_id=job.id,
        status=job.status,
        progress=job.progress,
        result=job.result,
        error=job.error,
    )


@app.get("/worker/jobs/{job_id}", response_model=WorkerJobStatusResponse)
def get_worker_job_status(job_id: str, db: Session = Depends(get_db)) -> WorkerJobStatusResponse:
    job = db.scalar(select(Job).where(Job.id == job_id))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return WorkerJobStatusResponse(
        job_id=job.id,
        status=job.status,
        progress=job.progress,
        result=job.result,
        error=job.error,
    )
