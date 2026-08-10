import os
import time
from datetime import datetime, timezone
from typing import Any

import requests


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
WORKER_ID = os.getenv("WORKER_ID", "llm-01")
WORKER_TYPE = os.getenv("WORKER_TYPE", "llm")
WORKER_HOSTNAME = os.getenv("WORKER_HOSTNAME", "llm-worker")
WORKER_CAPABILITIES = os.getenv(
    "WORKER_CAPABILITIES",
    "character_analysis,story_generation,script_generation,scene_json_generation",
).split(",")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "3"))


def register_worker() -> None:
    payload = {
        "worker_id": WORKER_ID,
        "worker_type": WORKER_TYPE,
        "hostname": WORKER_HOSTNAME,
        "capabilities": WORKER_CAPABILITIES,
        "models": ["mock-llm-v1"],
    }
    response = requests.post(f"{API_BASE_URL}/worker/register", json=payload, timeout=10)
    response.raise_for_status()


def send_heartbeat(status: str, current_job: str | None) -> None:
    payload = {
        "worker_id": WORKER_ID,
        "status": status,
        "current_job": current_job,
        "gpu": {
            "name": "LLM-MOCK",
            "vram_total": 0,
            "vram_used": 0,
        },
    }
    response = requests.post(
        f"{API_BASE_URL}/worker/heartbeat",
        json=payload,
        timeout=10,
    )
    response.raise_for_status()


def claim_job() -> dict[str, Any] | None:
    response = requests.post(
        f"{API_BASE_URL}/worker/jobs/claim",
        json={"worker_id": WORKER_ID},
        timeout=10,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def update_job_status(
    job_id: str,
    status: str,
    progress: float | None = None,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    payload: dict[str, Any] = {"status": status}
    if progress is not None:
        payload["progress"] = progress
    if result is not None:
        payload["result"] = result
    if error is not None:
        payload["error"] = error

    response = requests.post(
        f"{API_BASE_URL}/worker/jobs/{job_id}/status",
        json=payload,
        timeout=10,
    )
    response.raise_for_status()


def _character_analysis(user_input: dict[str, Any]) -> dict[str, Any]:
    character_name = user_input.get("name", "Unknown")
    description = user_input.get("description", "")
    return {
        "name": character_name,
        "summary": description or "No description provided",
        "personality": {"traits": ["calm", "kind"]},
        "appearance": {"style": "anime"},
    }


def _story_generation(user_input: dict[str, Any]) -> dict[str, Any]:
    topic = user_input.get("topic", "school life")
    return {
        "title": f"{topic.title()} - Pilot",
        "synopsis": f"A short anime story about {topic}.",
    }


def _script_generation(user_input: dict[str, Any]) -> dict[str, Any]:
    title = user_input.get("title", "Untitled")
    return {
        "title": title,
        "scenes": [
            {"scene_number": 1, "description": "Opening scene"},
            {"scene_number": 2, "description": "Conflict scene"},
            {"scene_number": 3, "description": "Resolution scene"},
        ],
    }


def _scene_json_generation(user_input: dict[str, Any]) -> dict[str, Any]:
    scene_id = user_input.get("scene_id", "scene_001")
    line = user_input.get("line", "我們開始吧。")
    return {
        "schema_version": "1.0",
        "scene_id": scene_id,
        "duration": 6,
        "location": {
            "id": "classroom",
            "description": "Classroom",
            "time": "afternoon",
            "weather": "clear",
        },
        "characters": [],
        "camera": {"shot": "medium", "angle": "eye_level", "movement": "static"},
        "dialogues": [{"sequence": 1, "character_id": "char_001", "text": line}],
        "visual": {"style": "anime", "prompt": "anime classroom scene", "negative_prompt": ""},
        "video": {"prompt": "subtle movement", "motion_strength": 0.3, "camera_motion": "static"},
        "audio": {"bgm": "light_piano", "ambient": ["room_tone"], "sfx": []},
    }


def run_llm_job(job: dict[str, Any]) -> dict[str, Any]:
    job_type = job["type"]
    user_input = job.get("input", {})

    if job_type == "character_analysis":
        return _character_analysis(user_input)
    if job_type == "story_generation":
        return _story_generation(user_input)
    if job_type == "script_generation":
        return _script_generation(user_input)
    if job_type == "scene_json_generation":
        return _scene_json_generation(user_input)
    raise ValueError(f"Unsupported llm job type: {job_type}")


def loop() -> None:
    register_worker()
    send_heartbeat(status="idle", current_job=None)

    while True:
        job = claim_job()
        if job is None:
            send_heartbeat(status="idle", current_job=None)
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        job_id = job["job_id"]
        send_heartbeat(status="busy", current_job=job_id)
        update_job_status(job_id=job_id, status="running", progress=0.1)

        try:
            result = run_llm_job(job)
            update_job_status(
                job_id=job_id,
                status="completed",
                progress=1.0,
                result={
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "output": result,
                },
            )
        except ValueError as error:
            update_job_status(job_id=job_id, status="failed", error=str(error))

        send_heartbeat(status="idle", current_job=None)


if __name__ == "__main__":
    loop()
