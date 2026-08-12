import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

import requests

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s [%(levelname)s] %(message)s",
    force=True,
)
logger = logging.getLogger("llm-worker")

# ──────────────────────────────────────────────
# Worker Config
# ──────────────────────────────────────────────
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
WORKER_ID = os.getenv("WORKER_ID", "llm-01")
WORKER_TYPE = os.getenv("WORKER_TYPE", "llm")
WORKER_HOSTNAME = os.getenv("WORKER_HOSTNAME", "llm-worker")
WORKER_CAPABILITIES = os.getenv(
    "WORKER_CAPABILITIES",
    "character_analysis,story_generation,script_generation,scene_json_generation",
).split(",")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "3"))

# ──────────────────────────────────────────────
# LLM Provider Config
# ──────────────────────────────────────────────
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()  # "gemini" or "local"

# Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Local LLM (OpenAI-compatible API)
LLM_API_URL = os.getenv("LLM_API_URL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "16384"))  # 增加到 16K tokens 以支援長腳本
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
LLM_TOP_P = float(os.getenv("LLM_TOP_P", "0.9"))

# ──────────────────────────────────────────────
# LLM Client
# ──────────────────────────────────────────────
gemini_client = None


def init_llm_client() -> None:
    """Initialize LLM client based on provider."""
    global gemini_client

    if LLM_PROVIDER == "gemini":
        if not GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not set, falling back to mock mode")
            return
        try:
            import google.generativeai as genai

            genai.configure(api_key=GEMINI_API_KEY)
            gemini_client = genai.GenerativeModel(GEMINI_MODEL)
            logger.info("Gemini client initialized: %s", GEMINI_MODEL)
        except Exception as e:
            logger.error("Failed to initialize Gemini client: %s, falling back to mock", e)
    elif LLM_PROVIDER == "local":
        if not LLM_API_URL:
            logger.warning("LLM_API_URL not set, falling back to mock mode")
            return
        logger.info("Local LLM configured: %s (model: %s)", LLM_API_URL, LLM_MODEL)
    else:
        logger.warning("Unknown LLM_PROVIDER '%s', falling back to mock mode", LLM_PROVIDER)


def call_llm(system_prompt: str, user_content: str) -> str:
    """
    Call LLM and return text response.
    Supports Gemini API and local OpenAI-compatible API.
    """
    if LLM_PROVIDER == "gemini" and gemini_client:
        return _call_gemini(system_prompt, user_content)
    elif LLM_PROVIDER == "local" and LLM_API_URL:
        return _call_local_llm(system_prompt, user_content)
    else:
        logger.warning("No LLM client available, returning empty response")
        return ""


def _call_gemini(system_prompt: str, user_content: str) -> str:
    """Call Gemini API."""
    try:
        full_prompt = f"{system_prompt}\n\n{user_content}"
        response = gemini_client.generate_content(full_prompt)
        text = response.text.strip()
        logger.info("Gemini response received: %d chars", len(text))
        return text
    except Exception as e:
        logger.error("Gemini API call failed: %s", e)
        raise


def _call_local_llm(system_prompt: str, user_content: str) -> str:
    """Call local LLM with OpenAI-compatible API."""
    try:
        url = LLM_API_URL.rstrip("/")
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"

        headers = {"Content-Type": "application/json"}
        if LLM_API_KEY:
            headers["Authorization"] = f"Bearer {LLM_API_KEY}"

        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": LLM_MAX_TOKENS,
            "temperature": LLM_TEMPERATURE,
            "top_p": LLM_TOP_P,
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        text = data["choices"][0]["message"]["content"].strip()
        logger.info("Local LLM response received: %d chars", len(text))
        return text
    except Exception as e:
        logger.error("Local LLM API call failed: %s", e)
        raise


def repair_truncated_json(text: str) -> str:
    """Attempt to repair truncated JSON by closing unclosed strings, arrays, and objects."""
    result = []
    in_string = False
    escape_next = False
    
    for char in text:
        if escape_next:
            result.append(char)
            escape_next = False
            continue
        
        if char == '\\' and in_string:
            result.append(char)
            escape_next = True
            continue
        
        if char == '"' and not escape_next:
            in_string = not in_string
            result.append(char)
            continue
        
        if in_string:
            result.append(char)
            continue
        
        # Outside of string
        if char in '{}[]':
            result.append(char)
        elif char == ',':
            result.append(char)
        elif char in ' \n\r\t':
            result.append(char)
    
    # If we're still in a string, close it
    if in_string:
        result.append('"')
    
    # Count unclosed brackets and braces
    stack = []
    for char in result:
        if char in '{[':
            stack.append(char)
        elif char == '}':
            if stack and stack[-1] == '{':
                stack.pop()
            else:
                stack.append('{')  # mismatched, treat as unclosed
        elif char == ']':
            if stack and stack[-1] == '[':
                stack.pop()
            else:
                stack.append('[')  # mismatched, treat as unclosed
    
    # Close any unclosed brackets/braces in reverse order
    while stack:
        opened = stack.pop()
        if opened == '{':
            result.append('}')
        elif opened == '[':
            result.append(']')
    
    return ''.join(result)


def parse_json_from_response(text: str) -> dict[str, Any]:
    """Extract JSON from LLM response (handles markdown code blocks & truncated JSON)."""
    text = text.strip()
    # Remove markdown code block wrappers
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # remove opening ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]  # remove closing ```
        text = "\n".join(lines)
    
    text = text.strip()
    
    # Try parsing directly first
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("Direct JSON parse failed: %s, attempting repair...", e)
    
    # Try repairing truncated JSON
    try:
        repaired = repair_truncated_json(text)
        return json.loads(repaired)
    except json.JSONDecodeError as repair_err:
        logger.error("JSON repair failed: %s", repair_err)
        raise




def register_worker() -> None:
    models = []
    if LLM_PROVIDER == "gemini" and GEMINI_API_KEY:
        models.append(GEMINI_MODEL)
    elif LLM_PROVIDER == "local" and LLM_MODEL:
        models.append(LLM_MODEL)
    else:
        models.append("mock-llm-v1")

    payload = {
        "worker_id": WORKER_ID,
        "worker_type": WORKER_TYPE,
        "hostname": WORKER_HOSTNAME,
        "capabilities": WORKER_CAPABILITIES,
        "models": models,
    }
    try:
        response = requests.post(f"{API_BASE_URL}/worker/register", json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Worker registered: %s (models: %s)", WORKER_ID, models)
    except Exception as e:
        logger.error("Failed to register worker: %s", e)


def send_heartbeat(status: str, current_job: str | None) -> None:
    payload = {
        "worker_id": WORKER_ID,
        "status": status,
        "current_job": current_job,
        "gpu": {
            "name": "LLM-%s" % LLM_PROVIDER.upper(),
            "vram_total": 0,
            "vram_used": 0,
        },
    }
    try:
        response = requests.post(
            f"{API_BASE_URL}/worker/heartbeat",
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
    except Exception as e:
        logger.error("Heartbeat failed: %s", e)


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

    try:
        response = requests.post(
            f"{API_BASE_URL}/worker/jobs/{job_id}/status",
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
    except Exception as e:
        logger.error("Failed to update job status %s: %s", job_id, e)


# ──────────────────────────────────────────────
# LLM Job Handlers
# ──────────────────────────────────────────────

CHARACTER_ANALYSIS_SYSTEM = """\
你是一位專業的動漫角色設計師。請根據用戶提供的資訊，生成一個完整的角色設定清單。
請以 JSON 陣列格式回覆，不要包含其他文字。

即使只有一個角色，也要用陣列格式。

JSON 格式:
[
  {
    "name": "角色名稱",
    "summary": "角色簡介 (1-2 句)",
    "personality": {
      "traits": ["特質1", "特質2", "特質3"],
      "strengths": ["優點1", "優點2"],
      "weaknesses": ["缺點1", "缺點2"],
      "motivation": "角色動機"
    },
    "appearance": {
      "style": "動漫風格描述",
      "hair": "髮型/髮色",
      "eyes": "眼睛描述",
      "clothing": "服裝風格",
      "distinctive_features": "獨特特徵"
    },
    "voice": {
      "tone": "聲音基調",
      "language": "主要語言"
    }
  }
]"""


def _character_analysis(user_input: dict[str, Any]) -> dict[str, Any]:
    brief = user_input.get("brief", "")
    project_name = user_input.get("project_name", "")
    name = user_input.get("name", "")
    description = user_input.get("description", "")
    extra = user_input.get("extra", "")

    # 支援兩種輸入格式
    if brief:
        user_content = f"""專案名稱: {project_name}
角色簡述: {brief}"""
    else:
        user_content = f"""角色名稱: {name}
基本描述: {description}
額外資訊: {extra}"""

    logger.info("Calling LLM for character_analysis: brief=%s", brief[:50] if brief else name)
    text = call_llm(CHARACTER_ANALYSIS_SYSTEM, user_content)
    if not text:
        raise RuntimeError("LLM returned empty response")

    try:
        result = parse_json_from_response(text)
        # 確保回傳格式是陣列
        if isinstance(result, dict):
            result = [result]
        logger.info("character_analysis completed: %d characters", len(result))
        return {"characters": result}
    except json.JSONDecodeError as e:
        logger.error("Failed to parse character_analysis JSON: %s\nRaw: %s", e, text)
        raise RuntimeError(f"Invalid JSON response from LLM: {e}")


STORY_GENERATION_SYSTEM = """\
你是一位專業的動漫劇本作家。請根據用戶提供的主題，生成一個短篇動漫故事大綱。
請以 JSON 格式回覆，不要包含其他文字。

JSON 格式:
{
  "title": "故事標題",
  "genre": "類型 (如: 校園/奇幻/科幻/戀愛)",
  "synopsis": "故事概要 (2-3 句)",
  "theme": "核心主題",
  "target_audience": "目標觀眾",
  "episode_count": 集數,
  "episode_outline": [
    {
      "episode": 1,
      "title": "集數標題",
      "summary": "集數概要"
    }
  ],
  "key_characters": [
    {"name": "角色名", "role": "主角/配角/反派", "brief": "簡短介紹"}
  ]
}"""


def _story_generation(user_input: dict[str, Any]) -> dict[str, Any]:
    topic = user_input.get("topic", "")
    genre = user_input.get("genre", "")
    episode_count = user_input.get("episode_count", 3)

    user_content = f"""主題: {topic}
類型偏好: {genre}
預計集數: {episode_count}"""

    logger.info("Calling LLM for story_generation: topic=%s", topic)
    text = call_llm(STORY_GENERATION_SYSTEM, user_content)
    if not text:
        raise RuntimeError("LLM returned empty response")

    try:
        result = parse_json_from_response(text)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse story_generation JSON: %s\nRaw: %s", e, text)
        raise RuntimeError(f"Invalid JSON response from LLM: {e}")

    logger.info("story_generation completed: %s", result.get("title"))
    return result


SCRIPT_GENERATION_SYSTEM = """\
你是一位專業的動漫分鏡腳本作家。請根據用戶提供的故事大綱，生成詳細的分鏡腳本。
請以 JSON 格式回覆，不要包含其他文字。

**重要：請確保 JSON 格式完整，所有括號和引號都要正確閉合。**

JSON 格式:
{
  "title": "腳本標題",
  "episode": 集數,
  "total_scenes": 總場景數,
  "scenes": [
    {
      "scene_number": 1,
      "location": "場景地點",
      "time": "時間 (白天/夜晚/傍晚)",
      "description": "場景描述 (簡短)",
      "characters_present": ["角色1", "角色2"],
      "dialogues": [
        {"character": "角色名", "line": "對白", "emotion": "情緒"}
      ],
      "camera_notes": "攝影機運鏡建議",
      "duration_seconds": 預計秒數
    }
  ]
}

**注意：每個場景的對話最多 3-4 句，保持簡潔。**"""


def _script_generation(user_input: dict[str, Any]) -> dict[str, Any]:
    title = user_input.get("title", "")
    story_outline = user_input.get("story_outline", "")
    characters = user_input.get("characters", [])

    char_list = json.dumps(characters, ensure_ascii=False) if characters else ""

    user_content = f"""標題: {title}
故事大綱: {story_outline}
角色列表: {char_list}

請生成 4-6 個場景的腳本，每個場景保持簡潔。"""

    logger.info("Calling LLM for script_generation: title=%s", title)
    text = call_llm(SCRIPT_GENERATION_SYSTEM, user_content)
    if not text:
        raise RuntimeError("LLM returned empty response")

    try:
        result = parse_json_from_response(text)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse script_generation JSON: %s\nRaw: %s", e, text)
        raise RuntimeError(f"Invalid JSON response from LLM: {e}")

    logger.info("script_generation completed: %s scenes", len(result.get("scenes", [])))
    return result


SCENE_JSON_GENERATION_SYSTEM = """\
你是一位動漫製作技術專家。請根據用戶提供的場景資訊，生成符合 AI Anime Studio 標準格式的場景 JSON。
請以 JSON 格式回覆，不要包含其他文字。

JSON 格式 (嚴格遵守以下 schema):
{
  "schema_version": "1.0",
  "scene_id": "場景 ID",
  "duration": 總秒數,
  "location": {
    "id": "地點 ID",
    "description": "地點描述",
    "time": "時間 (morning/afternoon/evening/night)",
    "weather": "天氣 (clear/rainy/snowy/cloudy)"
  },
  "characters": [
    {
      "id": "角色 ID",
      "name": "角色名稱",
      "position": "left/center/right",
      "expression": "表情",
      "pose": "姿勢"
    }
  ],
  "camera": {
    "shot": "極遠景/遠景/全景/中景/近景/特寫/極特寫",
    "angle": "俯角/平視/仰角",
    "movement": "靜止/橫移/推近/拉遠/環繞"
  },
  "dialogues": [
    {
      "sequence": 順序,
      "character_id": "角色 ID",
      "text": "對白文字",
      "emotion": "情緒"
    }
  ],
  "visual": {
    "style": "anime",
    "prompt": "用於 AI 繪圖的英文提示詞",
    "negative_prompt": "負面提示詞"
  },
  "video": {
    "prompt": "用於 AI 影片生成的英文提示詞",
    "motion_strength": 0.0到1.0,
    "camera_motion": "static/pan_left/pan_right/zoom_in/zoom_out"
  },
  "audio": {
    "bgm": "背景音樂風格",
    "ambient": ["環境音效"],
    "sfx": ["特效音效"]
  }
}"""


def _scene_json_generation(user_input: dict[str, Any]) -> dict[str, Any]:
    scene_id = user_input.get("scene_id", "scene_001")
    description = user_input.get("description", "")
    characters = user_input.get("characters", [])
    dialogues = user_input.get("dialogues", [])
    location = user_input.get("location", "")

    char_info = json.dumps(characters, ensure_ascii=False) if characters else ""
    dialogue_info = json.dumps(dialogues, ensure_ascii=False) if dialogues else ""

    user_content = f"""場景 ID: {scene_id}
場景描述: {description}
地點: {location}
角色資訊: {char_info}
對白資訊: {dialogue_info}"""

    logger.info("Calling LLM for scene_json_generation: scene_id=%s", scene_id)
    text = call_llm(SCENE_JSON_GENERATION_SYSTEM, user_content)
    if not text:
        raise RuntimeError("LLM returned empty response")

    try:
        result = parse_json_from_response(text)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse scene_json_generation JSON: %s\nRaw: %s", e, text)
        raise RuntimeError(f"Invalid JSON response from LLM: {e}")

    logger.info("scene_json_generation completed: %s", result.get("scene_id"))
    return result


def run_llm_job(job: dict[str, Any]) -> dict[str, Any]:
    job_type = job["type"]
    user_input = job.get("input", {})

    handlers = {
        "character_analysis": _character_analysis,
        "story_generation": _story_generation,
        "script_generation": _script_generation,
        "scene_json_generation": _scene_json_generation,
    }

    handler = handlers.get(job_type)
    if not handler:
        raise ValueError(f"Unsupported llm job type: {job_type}")

    return handler(user_input)


def loop() -> None:
    logger.info("=" * 60)
    logger.info("LLM Worker starting: %s", WORKER_ID)
    logger.info("Provider: %s", LLM_PROVIDER)
    if LLM_PROVIDER == "gemini":
        logger.info("Gemini Model: %s", GEMINI_MODEL)
        logger.info("Gemini API Key: %s...", GEMINI_API_KEY[:8] if GEMINI_API_KEY else "NOT SET")
    elif LLM_PROVIDER == "local":
        logger.info("Local LLM URL: %s", LLM_API_URL)
        logger.info("Local LLM Model: %s", LLM_MODEL)
    logger.info("Capabilities: %s", ", ".join(WORKER_CAPABILITIES))
    logger.info("=" * 60)

    # Initialize LLM client
    init_llm_client()

    # Register with API
    register_worker()
    send_heartbeat(status="idle", current_job=None)

    while True:
        try:
            job = claim_job()
            if job is None:
                send_heartbeat(status="idle", current_job=None)
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            job_id = job["job_id"]
            job_type = job["type"]
            logger.info("Received job: %s (type: %s)", job_id, job_type)

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
                logger.info("Job %s completed successfully", job_id)
            except Exception as error:
                logger.error("Job %s failed: %s", job_id, error, exc_info=True)
                update_job_status(job_id=job_id, status="failed", error=str(error))

            send_heartbeat(status="idle", current_job=None)
        except KeyboardInterrupt:
            logger.info("Worker shutting down (Ctrl+C)")
            break
        except Exception as e:
            logger.error("Unexpected error in main loop: %s", e, exc_info=True)
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    loop()
