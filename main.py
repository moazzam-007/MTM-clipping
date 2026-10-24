"""
main.py
FastAPI web service for Al Haqq Shorts & Mini-Long Video Repurposing Engine.
Features dedicated endpoints for Stage 1 (Topic Extraction) and Stage 2 (Single Clip Rendering)
with strict concurrency controls, path traversal prevention, and memory safety for Render free tier.
"""

import os
import time
import json
import uuid
import shutil
import secrets
import logging
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, Depends
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import config
from modules.youtube_engine import YouTubeEngine
from modules.transcription_engine import TranscriptionEngine
from modules.gemini_engine import GeminiEngine
from modules.video_engine import VideoEngine

logger = logging.getLogger("al-haqq-engine.api")

app = FastAPI(
    title="Al Haqq Video Repurposing Engine",
    description="Automated YouTube Lecture to Shorts & Mini-Long Video Generator",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Concurrency Gate: Strictly 1 heavy job at a time to stay under 512MB RAM cap
RENDER_SEMAPHORE = asyncio.Semaphore(1)

def sweep_expired_jobs(max_age_seconds: int = 1800):
    """Purges any temporary job folders older than max_age_seconds (default 30m)."""
    now = time.time()
    if not config.JOBS_DIR.exists():
        return
    for item in config.JOBS_DIR.iterdir():
        if item.is_dir():
            try:
                mtime = item.stat().st_mtime
                if (now - mtime) > max_age_seconds:
                    shutil.rmtree(item, ignore_errors=True)
                    logger.info(f"Purged expired job directory: {item.name}")
            except Exception as e:
                logger.warning(f"Failed to sweep {item}: {e}")

@app.on_event("startup")
def on_startup():
    sweep_expired_jobs(max_age_seconds=1800)

# ── Pydantic Request Models ─────────────────────────────────────────────────
class ExtractTopicsRequest(BaseModel):
    url: str
    max_clips: int = Field(default=8, ge=1, le=15)
    audio_sample_duration: Optional[int] = Field(default=None, description="Legacy parameter for backwards compatibility")
    max_duration_sec: int = Field(default=7200, ge=300, le=7200, description="Max duration to process (up to 120 mins)")
    chunk_duration_sec: int = Field(default=1200, ge=600, le=1800, description="Chunk length (20 mins default)")

class RenderClipRequest(BaseModel):
    url: str
    start_time: float = Field(ge=0)
    end_time: float = Field(gt=0)
    hook_text: str = Field(min_length=3, max_length=150)
    arabic_sub: Optional[str] = Field(default="", max_length=150)
    english_sub: Optional[str] = Field(default="", max_length=200)
    category: Optional[str] = "shorts"

# ── Security Dependency ─────────────────────────────────────────────────────
def verify_api_key(x_api_key: Optional[str] = Header(None)):
    if not config.API_SECRET_KEY:
        raise HTTPException(status_code=500, detail="API_SECRET_KEY is not configured on the server")
    if not x_api_key or not secrets.compare_digest(x_api_key, config.API_SECRET_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header")
    return True

# ── API Routes ──────────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "al-haqq-repurposing-engine",
        "gemini_model": config.GEMINI_PRIMARY_MODEL,
        "groq_model": config.GROQ_WHISPER_MODEL
    }

def _do_extract_topics(req: ExtractTopicsRequest, job_dir: Path) -> Dict[str, Any]:
    yt_info = YouTubeEngine.get_video_info(req.url)
    audio_stream_url = yt_info.get("audio_stream_url") or yt_info["stream_url"]
    video_duration = yt_info.get("duration", 0.0) or 3600.0

    # Determine processing duration:
    # If legacy audio_sample_duration was explicitly passed by n8n, honor it, otherwise process full bayan up to max_duration_sec
    process_duration = req.audio_sample_duration if req.audio_sample_duration else min(video_duration, float(req.max_duration_sec))

    # Chunked Audio Extraction (20-min chunks at 32kbps mono starting from 0s)
    start_sec = 0
    chunks = YouTubeEngine.extract_audio_chunks(
        stream_url=audio_stream_url,
        output_dir=job_dir / "audio_chunks",
        total_duration_sec=process_duration,
        start_sec=start_sec,
        chunk_duration_sec=req.chunk_duration_sec,
        max_duration_sec=req.max_duration_sec
    )

    # Multi-chunk Whisper Transcription (aggregated into a single seamless timeline)
    trans_engine = TranscriptionEngine()
    transcript = trans_engine.transcribe_chunks(
        chunks=chunks,
        cache_path=job_dir / "transcript.json"
    )

    # Gemini Topic Extraction (timestamps are already globally offset in transcript segments)
    gemini_engine = GeminiEngine()
    topics = gemini_engine.extract_topics(
        transcript_data=transcript,
        max_clips=req.max_clips,
        offset_sec=0.0
    )

    return {
        "status": "ok",
        "video_id": yt_info.get("video_id"),
        "title": yt_info.get("title"),
        "total_topics": len(topics),
        "topics": topics
    }

# ── STAGE 1 ENDPOINT: Extract Topics without Video Rendering ─────────────────
@app.post("/api/extract-topics")
async def extract_topics(req: ExtractTopicsRequest, auth: bool = Depends(verify_api_key)):
    """
    Stage 1 endpoint:
    Streams audio in chunks, transcribes with Groq Whisper, and extracts topics with Gemini.
    Guarded by RENDER_SEMAPHORE so extraction and video composition never run concurrently in 512MB RAM.
    """
    job_id = f"extract_{uuid.uuid4().hex[:8]}"
    job_dir = config.JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    async with RENDER_SEMAPHORE:
        logger.info(f"Acquired lock for Stage 1 Extraction: {req.url}")
        try:
            res = await asyncio.to_thread(_do_extract_topics, req, job_dir)
            return res
        finally:
            # Full directory cleanup to guarantee 0% disk leak
            shutil.rmtree(job_dir, ignore_errors=True)

def _execute_render_job(req: RenderClipRequest, clip_id: str, clip_dir: Path, final_mp4_path: Path, raw_clip_path: Path) -> Dict[str, Any]:
    duration = req.end_time - req.start_time
    yt_info = YouTubeEngine.get_video_info(req.url)
    stream_url = yt_info["stream_url"]
    audio_stream_url = yt_info.get("audio_stream_url", "")

    # Cut HD clip (handles single and dual stream)
    YouTubeEngine.cut_hd_clip(
        stream_url=stream_url,
        start_sec=req.start_time,
        duration_sec=duration,
        output_path=raw_clip_path,
        audio_stream_url=audio_stream_url
    )

    # Render onto template with face centering and subtitles
    video_engine = VideoEngine()
    video_engine.render_final_video(
        raw_clip_path=raw_clip_path,
        hook_text=req.hook_text,
        arabic_text=req.arabic_sub or "",
        english_text=req.english_sub or "",
        output_mp4_path=final_mp4_path
    )

    return {
        "status": "completed",
        "clip_id": clip_id,
        "category": req.category,
        "duration": round(duration, 1),
        "download_url": f"/api/download/{clip_id}/{final_mp4_path.name}"
    }

# ── STAGE 2 ENDPOINT: Render a Single Pre-selected Clip ─────────────────────
@app.post("/api/render-clip")
async def render_single_clip(req: RenderClipRequest, auth: bool = Depends(verify_api_key)):
    """
    Stage 2 endpoint:
    Takes one topic row from Google Sheet, cuts 720p HD clip, and renders the 9:16 short.
    Protected by Semaphore(1) and runs in worker thread (asyncio.to_thread) so FastAPI event loop
    and /health remain 100% responsive.
    """
    duration = req.end_time - req.start_time
    if duration <= 0 or duration > config.MINI_LONG_MAX_DURATION:
        raise HTTPException(status_code=400, detail=f"Invalid duration: {duration:.1f}s")

    # Sanitize category for safe file naming
    clean_category = "".join(c for c in (req.category or "shorts") if c.isalnum() or c in "-_")
    if not clean_category:
        clean_category = "shorts"

    clip_id = f"clip_{uuid.uuid4().hex[:8]}"
    clip_dir = config.JOBS_DIR / clip_id
    clip_dir.mkdir(parents=True, exist_ok=True)

    raw_clip_path = clip_dir / "raw.mp4"
    final_mp4_path = clip_dir / f"{clip_id}_{clean_category}.mp4"

    async with RENDER_SEMAPHORE:
        logger.info(f"Acquired render lock for clip {clip_id} ({duration:.1f}s)")
        try:
            result = await asyncio.to_thread(
                _execute_render_job,
                req=req,
                clip_id=clip_id,
                clip_dir=clip_dir,
                final_mp4_path=final_mp4_path,
                raw_clip_path=raw_clip_path
            )
            return result
        except Exception:
            # On failure, clean up entire clip directory
            shutil.rmtree(clip_dir, ignore_errors=True)
            raise
        finally:
            if raw_clip_path.exists():
                raw_clip_path.unlink()

# ── MILAN VOIMA ASYNC POLLING ARCHITECTURE (50s Poll + Sleep Prevention) ────
JOBS_STORE: Dict[str, Dict[str, Any]] = {}

async def _run_async_render_worker(req: RenderClipRequest, clip_id: str):
    clean_category = "".join(c for c in (req.category or "shorts") if c.isalnum() or c in "-_") or "shorts"
    clip_dir = config.JOBS_DIR / clip_id
    clip_dir.mkdir(parents=True, exist_ok=True)
    raw_clip_path = clip_dir / "raw.mp4"
    final_mp4_path = clip_dir / f"{clip_id}_{clean_category}.mp4"

    async with RENDER_SEMAPHORE:
        try:
            JOBS_STORE[clip_id]["status"] = "processing"
            JOBS_STORE[clip_id]["progress"] = 25
            result = await asyncio.to_thread(
                _execute_render_job,
                req=req,
                clip_id=clip_id,
                clip_dir=clip_dir,
                final_mp4_path=final_mp4_path,
                raw_clip_path=raw_clip_path
            )
            JOBS_STORE[clip_id]["status"] = "completed"
            JOBS_STORE[clip_id]["progress"] = 100
            JOBS_STORE[clip_id]["download_url"] = result["download_url"]
            logger.info(f"Async job {clip_id} completed successfully!")
        except Exception as e:
            logger.error(f"Async job {clip_id} failed: {e}")
            JOBS_STORE[clip_id]["status"] = "failed"
            JOBS_STORE[clip_id]["error"] = str(e)
            shutil.rmtree(clip_dir, ignore_errors=True)
        finally:
            if raw_clip_path.exists():
                raw_clip_path.unlink()

@app.post("/api/render-clip-async")
async def render_clip_async(req: RenderClipRequest, auth: bool = Depends(verify_api_key)):
    """
    Milan Voima asynchronous job dispatch.
    Immediately returns job_id so n8n can poll /api/job-status/{clip_id} every 50 seconds.
    Prevents HTTP proxy timeouts and resets Render 15-minute idle sleep timer on every poll ping.
    """
    duration = req.end_time - req.start_time
    if duration <= 0 or duration > config.MINI_LONG_MAX_DURATION:
        raise HTTPException(status_code=400, detail=f"Invalid duration: {duration:.1f}s")

    clip_id = f"clip_{uuid.uuid4().hex[:8]}"
    JOBS_STORE[clip_id] = {
        "clip_id": clip_id,
        "status": "queued",
        "progress": 5,
        "created_at": time.time(),
        "duration": round(duration, 1),
        "download_url": None,
        "error": None
    }

    # Launch worker in background task
    asyncio.create_task(_run_async_render_worker(req, clip_id))

    return {
        "status": "queued",
        "clip_id": clip_id,
        "check_url": f"/api/job-status/{clip_id}"
    }

@app.get("/api/job-status/{clip_id}")
def get_job_status(clip_id: str, auth: bool = Depends(verify_api_key)):
    """
    Polling endpoint called by n8n every 50 seconds (up to 50 iterations).
    Resets Render 15-minute idle sleep timer on every request.
    """
    job = JOBS_STORE.get(clip_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job ID not found")
    return job

# ── SECURE DOWNLOAD ENDPOINT (Path Traversal Protected + Ephemeral Cleanup) ─
@app.get("/api/download/{job_id}/{clip_filename}")
def download_clip(
    job_id: str,
    clip_filename: str,
    background_tasks: BackgroundTasks,
    auth: bool = Depends(verify_api_key)
):
    # Sanitize inputs to prevent path traversal
    safe_job_id = Path(job_id).name
    safe_filename = Path(clip_filename).name

    target_path = (config.JOBS_DIR / safe_job_id / safe_filename).resolve()
    base_jobs_path = config.JOBS_DIR.resolve()

    # Strict check: path must be inside JOBS_DIR
    try:
        target_path.relative_to(base_jobs_path)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied: Invalid file path")

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="Requested video file not found")

    # Auto-cleanup file and parent dir once downloaded so Render container disk never fills up
    def cleanup_downloaded_file(file_to_del: Path):
        try:
            if file_to_del.exists():
                file_to_del.unlink()
                parent_dir = file_to_del.parent
                if parent_dir.exists() and not any(parent_dir.iterdir()):
                    parent_dir.rmdir()
                logger.info(f"Purged ephemeral render file {file_to_del.name}")
        except Exception as err:
            logger.warning(f"Error during file cleanup: {err}")

    background_tasks.add_task(cleanup_downloaded_file, target_path)

    return FileResponse(
        path=str(target_path),
        media_type="video/mp4",
        filename=safe_filename
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=config.PORT, reload=False)
