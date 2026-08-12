import logging
import os
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s [%(levelname)s] %(message)s",
    force=True,
)
logger = logging.getLogger("orchestrator")

# ──────────────────────────────────────────────
# Database
# ──────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./anime.db")
POLL_SECONDS = int(os.getenv("ORCHESTRATOR_POLL_SECONDS", "3"))

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def create_tables() -> None:
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ensured: %s", DATABASE_URL)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    source_prompt: Mapped[str | None] = mapped_column(Text)
    workflow_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    character_profile: Mapped[dict | None] = mapped_column(JSON)
    story_data: Mapped[dict | None] = mapped_column(JSON)
    script_data: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Episode(Base):
    __tablename__ = "episodes"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(100), ForeignKey("projects.id"))
    episode_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    synopsis: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Scene(Base):
    __tablename__ = "scenes"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    episode_id: Mapped[str] = mapped_column(String(100), ForeignKey("episodes.id"))
    scene_number: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    scene_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Worker(Base):
    __tablename__ = "workers"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    worker_type: Mapped[str] = mapped_column(String(50), nullable=False)
    hostname: Mapped[str | None] = mapped_column(String(255))
    endpoint: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    gpu: Mapped[str | None] = mapped_column(String(255))
    vram: Mapped[int | None] = mapped_column(Integer)
    capabilities: Mapped[dict] = mapped_column(JSON, default=list, nullable=False)
    models: Mapped[dict] = mapped_column(JSON, default=list, nullable=False)
    gpu_info: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    current_job: Mapped[str | None] = mapped_column(String(100))
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(String(100))
    episode_id: Mapped[str | None] = mapped_column(String(100))
    scene_id: Mapped[str | None] = mapped_column(String(100))
    worker_id: Mapped[str | None] = mapped_column(String(100), ForeignKey("workers.id"))
    worker_type: Mapped[str | None] = mapped_column(String(50))
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    progress: Mapped[float | None] = mapped_column(Float)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def latest_completed_job(db, project_id: str, job_type: str) -> Job | None:
    return db.scalar(
        select(Job)
        .where(
            Job.project_id == project_id,
            Job.job_type == job_type,
            Job.status == "completed",
        )
        .order_by(Job.completed_at.desc())
        .limit(1)
    )


def has_active_job(db, project_id: str, job_type: str) -> bool:
    job = db.scalar(
        select(Job)
        .where(
            Job.project_id == project_id,
            Job.job_type == job_type,
            Job.status.in_(("queued", "running")),
        )
        .limit(1)
    )
    return job is not None


def has_scene_job(db, project_id: str, scene_id: str, job_type: str) -> bool:
    job = db.scalar(
        select(Job)
        .where(
            Job.project_id == project_id,
            Job.scene_id == scene_id,
            Job.job_type == job_type,
            Job.status.in_(("queued", "running", "completed")),
        )
        .limit(1)
    )
    return job is not None


def enqueue_llm_job(
    db, *, project_id: str, episode_id: str | None, scene_id: str | None, job_type: str, payload: dict
) -> None:
    db.add(
        Job(
            id=new_id("job"),
            project_id=project_id,
            episode_id=episode_id,
            scene_id=scene_id,
            worker_type="llm",
            job_type=job_type,
            status="queued",
            priority=2,
            attempt=0,
            max_attempts=3,
            payload={"input": payload},
            created_at=now_utc(),
        )
    )


# GPU Worker 類型對應
GPU_WORKER_TYPES = {
    "character_image": "image",
    "scene_image": "image",
    "background_image": "image",
    "scene_video": "video",
    "character_animation": "video",
    "camera_motion": "video",
    "voice_synthesis": "audio",
    "voice_recognition": "audio",
    "bgm_generation": "audio",
    "audio_mixing": "audio",
    "video_composition": "editor",
    "final_render": "editor",
    "subtitle_burn": "editor",
    "video_concat": "editor",
    "audio_sync": "editor",
}


def enqueue_gpu_job(
    db,
    *,
    project_id: str,
    episode_id: str | None,
    scene_id: str | None,
    job_type: str,
    payload: dict,
    priority: int = 5,
) -> None:
    """建立 GPU 作業 (image/video/audio/editor)"""
    worker_type = GPU_WORKER_TYPES.get(job_type, "image")
    db.add(
        Job(
            id=new_id("job"),
            project_id=project_id,
            episode_id=episode_id,
            scene_id=scene_id,
            worker_type=worker_type,
            job_type=job_type,
            status="queued",
            priority=priority,
            attempt=0,
            max_attempts=3,
            payload={"input": payload},
            created_at=now_utc(),
        )
    )


def process_failed_jobs(db) -> None:
    failed_jobs = db.scalars(select(Job).where(Job.status == "failed")).all()
    for job in failed_jobs:
        if job.attempt < job.max_attempts:
            job.status = "queued"
            job.worker_id = None
            job.started_at = None
        elif job.project_id:
            project = db.get(Project, job.project_id)
            if project is not None:
                project.status = "failed"
                project.updated_at = now_utc()


def process_project(db, project: Project) -> None:
    workflow = project.workflow_data or {}
    episode_id = workflow.get("episode_id")
    if not episode_id:
        return

    if project.status == "character_analysis_pending":
        completed = latest_completed_job(db, project.id, "character_analysis")
        if completed is not None:
            project.character_profile = (completed.result or {}).get("output")
            project.status = "story_generation_pending"
            if not has_active_job(db, project.id, "story_generation"):
                enqueue_llm_job(
                    db,
                    project_id=project.id,
                    episode_id=episode_id,
                    scene_id=None,
                    job_type="story_generation",
                    payload={
                        "topic": project.source_prompt or project.name,
                        "character_profile": project.character_profile or {},
                    },
                )

    elif project.status == "story_generation_pending":
        completed = latest_completed_job(db, project.id, "story_generation")
        if completed is not None:
            project.story_data = (completed.result or {}).get("output")
            project.status = "script_generation_pending"
            if not has_active_job(db, project.id, "script_generation"):
                enqueue_llm_job(
                    db,
                    project_id=project.id,
                    episode_id=episode_id,
                    scene_id=None,
                    job_type="script_generation",
                    payload={
                        "title": (project.story_data or {}).get("title", project.name),
                        "synopsis": (project.story_data or {}).get("synopsis", ""),
                    },
                )

    elif project.status == "script_generation_pending":
        completed = latest_completed_job(db, project.id, "script_generation")
        if completed is not None:
            project.script_data = (completed.result or {}).get("output")
            scenes = db.scalars(select(Scene).where(Scene.episode_id == episode_id)).all()
            if not scenes:
                return
            for scene in scenes:
                if not has_scene_job(db, project.id, scene.id, "scene_json_generation"):
                    enqueue_llm_job(
                        db,
                        project_id=project.id,
                        episode_id=episode_id,
                        scene_id=scene.id,
                        job_type="scene_json_generation",
                        payload={
                            "scene_id": scene.id,
                            "line": f"Scene {scene.scene_number} line",
                        },
                    )
            project.status = "scene_json_generation_pending"

    elif project.status == "scene_json_generation_pending":
        scenes = db.scalars(select(Scene).where(Scene.episode_id == episode_id)).all()
        if not scenes:
            return

        completed_scene_jobs = db.scalars(
            select(Job).where(
                Job.project_id == project.id,
                Job.job_type == "scene_json_generation",
                Job.status == "completed",
            )
        ).all()
        completed_map = {j.scene_id: j for j in completed_scene_jobs if j.scene_id}

        all_completed = True
        for scene in scenes:
            completed_job = completed_map.get(scene.id)
            if completed_job is None:
                all_completed = False
                continue
            scene.scene_data = (completed_job.result or {}).get("output", {})
            scene.status = "ready_for_image"
            scene.updated_at = now_utc()

        if all_completed:
            episode = db.get(Episode, episode_id)
            if episode is not None:
                episode.status = "ready_for_gpu_pipeline"
                episode.updated_at = now_utc()
            project.status = "ready_for_gpu_pipeline"
            project.updated_at = now_utc()

    # === GPU 管線階段 1: 角色圖像生成 ===
    elif project.status == "ready_for_gpu_pipeline":
        # 檢查是否已經有角色圖像作業
        if not has_active_job(db, project.id, "character_image"):
            # 從 character_profile 取得角色清單
            characters = project.character_profile or {}
            if isinstance(characters, list):
                for char in characters:
                    char_name = char.get("name", "unknown")
                    char_desc = char.get("appearance", "")
                    if not has_active_job(db, project.id, f"character_image_{char_name}"):
                        enqueue_gpu_job(
                            db,
                            project_id=project.id,
                            episode_id=episode_id,
                            scene_id=None,
                            job_type="character_image",
                            payload={
                                "character_name": char_name,
                                "character_description": char_desc,
                                "style": "anime",
                                "width": 1024,
                                "height": 1024,
                            },
                        )
            project.status = "character_image_pending"
            project.updated_at = now_utc()

    # === GPU 管線階段 2: 場景圖像生成 ===
    elif project.status == "character_image_pending":
        completed = latest_completed_job(db, project.id, "character_image")
        if completed is not None:
            scenes = db.scalars(select(Scene).where(Scene.episode_id == episode_id)).all()
            for scene in scenes:
                scene_data = scene.scene_data or {}
                scene_desc = scene_data.get("description", "")
                if not has_scene_job(db, project.id, scene.id, "scene_image"):
                    enqueue_gpu_job(
                        db,
                        project_id=project.id,
                        episode_id=episode_id,
                        scene_id=scene.id,
                        job_type="scene_image",
                        payload={
                            "scene_description": scene_desc,
                            "characters": project.character_profile or [],
                            "style": "anime",
                            "width": 1920,
                            "height": 1080,
                        },
                    )
            project.status = "scene_image_pending"
            project.updated_at = now_utc()

    # === GPU 管線階段 3: 場景影片生成 ===
    elif project.status == "scene_image_pending":
        scenes = db.scalars(select(Scene).where(Scene.episode_id == episode_id)).all()
        if not scenes:
            return
        completed_scene_images = db.scalars(
            select(Job).where(
                Job.project_id == project.id,
                Job.job_type == "scene_image",
                Job.status == "completed",
            )
        ).all()
        completed_map = {j.scene_id: j for j in completed_scene_images if j.scene_id}
        all_completed = True
        for scene in scenes:
            completed_job = completed_map.get(scene.id)
            if completed_job is None:
                all_completed = False
                continue
        if all_completed:
            for scene in scenes:
                if not has_scene_job(db, project.id, scene.id, "scene_video"):
                    scene_data = scene.scene_data or {}
                    enqueue_gpu_job(
                        db,
                        project_id=project.id,
                        episode_id=episode_id,
                        scene_id=scene.id,
                        job_type="scene_video",
                        payload={
                            "scene_image_url": (completed_map[scene.id].result or {}).get("image_url"),
                            "scene_description": scene_data.get("description", ""),
                            "duration": scene.duration_seconds or 10.0,
                            "fps": 24,
                        },
                    )
            project.status = "scene_video_pending"
            project.updated_at = now_utc()

    # === GPU 管線階段 4: 語音合成 ===
    elif project.status == "scene_video_pending":
        scenes = db.scalars(select(Scene).where(Scene.episode_id == episode_id)).all()
        if not scenes:
            return
        completed_scene_videos = db.scalars(
            select(Job).where(
                Job.project_id == project.id,
                Job.job_type == "scene_video",
                Job.status == "completed",
            )
        ).all()
        completed_map = {j.scene_id: j for j in completed_scene_videos if j.scene_id}
        all_completed = True
        for scene in scenes:
            completed_job = completed_map.get(scene.id)
            if completed_job is None:
                all_completed = False
                continue
        if all_completed:
            # 為每個場景的對話生成語音
            scenes = db.scalars(select(Scene).where(Scene.episode_id == episode_id)).all()
            for scene in scenes:
                scene_data = scene.scene_data or {}
                dialogues = scene_data.get("dialogues", [])
                for dialogue in dialogues:
                    char_name = dialogue.get("character", "unknown")
                    text = dialogue.get("text", "")
                    if not has_scene_job(db, project.id, scene.id, f"voice_synthesis_{char_name}"):
                        enqueue_gpu_job(
                            db,
                            project_id=project.id,
                            episode_id=episode_id,
                            scene_id=scene.id,
                            job_type="voice_synthesis",
                            payload={
                                "text": text,
                                "character_name": char_name,
                                "voice_config": (project.character_profile or {}).get(char_name, {}),
                            },
                        )
            project.status = "voice_synthesis_pending"
            project.updated_at = now_utc()

    # === GPU 管線階段 5: 背景音樂生成 ===
    elif project.status == "voice_synthesis_pending":
        completed = latest_completed_job(db, project.id, "voice_synthesis")
        if completed is not None:
            if not has_active_job(db, project.id, "bgm_generation"):
                enqueue_gpu_job(
                    db,
                    project_id=project.id,
                    episode_id=episode_id,
                    scene_id=None,
                    job_type="bgm_generation",
                    payload={
                        "mood": (project.story_data or {}).get("mood", "neutral"),
                        "genre": "anime",
                        "duration": 180.0,
                    },
                )
            project.status = "bgm_generation_pending"
            project.updated_at = now_utc()

    # === GPU 管線階段 6: 影片合成 ===
    elif project.status == "bgm_generation_pending":
        completed = latest_completed_job(db, project.id, "bgm_generation")
        if completed is not None:
            scenes = db.scalars(select(Scene).where(Scene.episode_id == episode_id)).all()
            for scene in scenes:
                if not has_scene_job(db, project.id, scene.id, "video_composition"):
                    enqueue_gpu_job(
                        db,
                        project_id=project.id,
                        episode_id=episode_id,
                        scene_id=scene.id,
                        job_type="video_composition",
                        payload={
                            "scene_id": scene.id,
                            "bgm_url": (completed.result or {}).get("audio_url"),
                        },
                    )
            project.status = "video_composition_pending"
            project.updated_at = now_utc()

    # === GPU 管線階段 7: 最終渲染 ===
    elif project.status == "video_composition_pending":
        scenes = db.scalars(select(Scene).where(Scene.episode_id == episode_id)).all()
        if not scenes:
            return
        completed_compositions = db.scalars(
            select(Job).where(
                Job.project_id == project.id,
                Job.job_type == "video_composition",
                Job.status == "completed",
            )
        ).all()
        completed_map = {j.scene_id: j for j in completed_compositions if j.scene_id}
        all_completed = True
        for scene in scenes:
            completed_job = completed_map.get(scene.id)
            if completed_job is None:
                all_completed = False
                continue
        if all_completed:
            if not has_active_job(db, project.id, "final_render"):
                enqueue_gpu_job(
                    db,
                    project_id=project.id,
                    episode_id=episode_id,
                    scene_id=None,
                    job_type="final_render",
                    payload={
                        "scenes": [
                            {
                                "scene_id": scene.id,
                                "video_url": (completed_map[scene.id].result or {}).get("video_url"),
                                "duration": scene.duration_seconds or 10.0,
                            }
                            for scene in scenes
                        ],
                        "transitions": ["fade"],
                        "output_name": f"episode_{episode_id}_final",
                    },
                )
            project.status = "final_render_pending"
            project.updated_at = now_utc()

    # === GPU 管線完成 ===
    elif project.status == "final_render_pending":
        completed = latest_completed_job(db, project.id, "final_render")
        if completed is not None:
            project.status = "completed"
            project.updated_at = now_utc()
            episode = db.get(Episode, episode_id)
            if episode is not None:
                episode.status = "completed"
                episode.updated_at = now_utc()


def run_once() -> None:
    with SessionLocal() as db:
        process_failed_jobs(db)
        projects = db.scalars(
            select(Project).where(
                Project.status.in_(
                    (
                        "character_analysis_pending",
                        "story_generation_pending",
                        "script_generation_pending",
                        "scene_json_generation_pending",
                        "ready_for_gpu_pipeline",
                        "character_image_pending",
                        "scene_image_pending",
                        "scene_video_pending",
                        "voice_synthesis_pending",
                        "bgm_generation_pending",
                        "video_composition_pending",
                        "final_render_pending",
                    )
                )
            )
        ).all()
        for project in projects:
            process_project(db, project)
        db.commit()


def main() -> None:
    logger.info("=" * 60)
    logger.info("Orchestrator starting")
    logger.info("Database: %s", DATABASE_URL)
    logger.info("Poll interval: %ds", POLL_SECONDS)
    logger.info("=" * 60)

    # Create tables if they don't exist
    create_tables()

    while True:
        try:
            run_once()
        except Exception as e:
            logger.error("Error in run_once: %s", e, exc_info=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
