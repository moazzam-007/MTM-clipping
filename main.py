"""
main.py
FastAPI web service for Al Haqq Shorts & Mini-Long Video Repurposing Engine.
Designed for 100% free-tier memory safety on Render.com and direct n8n webhook integration.
"""

import os
import json
import uuid
import logging
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, Depends
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
import requests
import config
from modules.youtube_engine import YouTubeEngine
from modules.transcription_engine import TranscriptionEngine
from modules.gemini_engine import GeminiEngine
from modules.video_engine import VideoEngine

logger = logging.getLogger("al-haqq-engine.api")

app = FastAPI(
    title="Al Haqq Video Repurposing Engine",
    description="Automated YouTube Lecture to Shorts & Mini-Long Video Generator",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory Job State Store
JOBS: Dict[str, Dict[str, Any]] = {}

# ── Pydantic Request Models ─────────────────────────────────────────────────
class ProcessVideoRequest(BaseModel):
    url: str
    max_clips: Optional[int] = 5
    audio_sample_duration: Optional[int] = 1200 # 20 mins sample
    webhook_url: Optional[str] = None

# ── Security Dependency ─────────────────────────────────────────────────────
def verify_api_key(x_api_key: Optional[str] = Header(None)):
    if config.API_SECRET_KEY and x_api_key != config.API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header")
    return True

# ── Background Task Pipeline ────────────────────────────────────────────────
def run_job_pipeline(job_id: str, req: ProcessVideoRequest):
    job_dir = config.JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    status_file = job_dir / "status.json"
    
    def update_status(status: str, progress: int, step: str, extra: Dict[str, Any] = None):
        state = {
            "job_id": job_id,
            "status": status,
            "progress": progress,
            "step": step,
            "error": None
        }
        if extra:
            state.update(extra)
        JOBS[job_id] = state
        with open(status_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    try:
        # Step 1: Resolve Video & Stream URL
        update_status("processing", 10, "resolving_youtube_stream")
        yt_info = YouTubeEngine.get_video_info(req.url)
        stream_url = yt_info["stream_url"]
        
        # Step 2: Stream Sample Audio
        update_status("processing", 25, "extracting_sample_audio")
        audio_path = job_dir / "lecture_audio.mp3"
        YouTubeEngine.extract_audio(
            stream_url=stream_url,
            output_path=audio_path,
            start_sec=120,
            duration_sec=req.audio_sample_duration
        )
        
        # Step 3: Groq Whisper Transcription
        update_status("processing", 45, "transcribing_audio")
        trans_engine = TranscriptionEngine()
        transcript = trans_engine.transcribe(
            audio_path=audio_path,
            cache_path=job_dir / "transcript.json"
        )
        
        # Step 4: AI Topic Extraction & Classification
        update_status("processing", 60, "ai_topic_analysis")
        gemini_engine = GeminiEngine()
        topics = gemini_engine.extract_topics(
            transcript_data=transcript,
            max_clips=req.max_clips,
            offset_sec=120.0
        )
        
        # Step 5: Render Each Clip
        rendered_clips = []
        video_engine = VideoEngine()
        total_topics = len(topics)
        
        for idx, topic in enumerate(topics, start=1):
            clip_id = f"clip_{idx:02d}"
            category = topic.get("category", "shorts")
            start_t = topic["start_time"]
            end_t = topic["end_time"]
            duration = end_t - start_t
            
            step_name = f"rendering_clip_{idx}_of_{total_topics}"
            pct = 60 + int((idx / total_topics) * 35)
            update_status("processing", pct, step_name)
            
            # Cut raw HD segment
            raw_clip_path = job_dir / f"{clip_id}_raw.mp4"
            YouTubeEngine.cut_hd_clip(
                stream_url=stream_url,
                start_sec=start_t,
                duration_sec=duration,
                output_path=raw_clip_path
            )
            
            # Final composition with template + subtitles
            final_clip_name = f"{clip_id}_{category}.mp4"
            final_clip_path = job_dir / final_clip_name
            video_engine.render_final_video(
                raw_clip_path=raw_clip_path,
                hook_text=topic.get("roman_urdu_hook", ""),
                arabic_text=topic.get("arabic_sub", ""),
                english_text=topic.get("english_sub", ""),
                output_mp4_path=final_clip_path
            )
            
            rendered_clips.append({
                "clip_id": clip_id,
                "category": category,
                "filename": final_clip_name,
                "download_url": f"/api/download/{job_id}/{final_clip_name}",
                "duration": duration,
                "roman_urdu_hook": topic.get("roman_urdu_hook"),
                "yt_title": topic.get("yt_title"),
                "yt_description": topic.get("yt_description"),
                "tags": topic.get("tags", [])
            })
            
            # Remove raw cut to preserve server disk
            if raw_clip_path.exists():
                raw_clip_path.unlink()

        # Step 6: Mark Complete
        update_status("completed", 100, "done", {"clips": rendered_clips, "total_clips": len(rendered_clips)})
        logger.info(f"Job {job_id} successfully completed with {len(rendered_clips)} clips!")

        # Step 7: Notify n8n Webhook
        if req.webhook_url:
            logger.info(f"Notifying webhook: {req.webhook_url}")
            try:
                requests.post(
                    req.webhook_url,
                    json={
                        "job_id": job_id,
                        "status": "completed",
                        "video_title": yt_info.get("title"),
                        "clips": rendered_clips
                    },
                    timeout=15
                )
            except Exception as wh_err:
                logger.warning(f"Failed to ping webhook: {wh_err}")

    except Exception as err:
        logger.exception(f"Job {job_id} failed with error: {err}")
        update_status("failed", 0, "error", {"error": str(err)})

# ── API Routes ──────────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "al-haqq-repurposing-engine",
        "gemini_model": config.GEMINI_PRIMARY_MODEL,
        "groq_model": config.GROQ_WHISPER_MODEL
    }

@app.post("/api/process-video")
def process_video(
    req: ProcessVideoRequest,
    bg_tasks: BackgroundTasks,
    auth: bool = Depends(verify_api_key)
):
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    JOBS[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "progress": 0,
        "step": "queued",
        "clips": []
    }
    bg_tasks.add_task(run_job_pipeline, job_id, req)
    return {
        "job_id": job_id,
        "status": "queued",
        "status_url": f"/api/status/{job_id}"
    }

@app.get("/api/status/{job_id}")
def get_job_status(job_id: str):
    if job_id in JOBS:
        return JOBS[job_id]
        
    status_file = config.JOBS_DIR / job_id / "status.json"
    if status_file.exists():
        with open(status_file, "r", encoding="utf-8") as f:
            return json.load(f)
            
    raise HTTPException(status_code=404, detail="Job not found")

@app.get("/api/download/{job_id}/{clip_filename}")
def download_clip(job_id: str, clip_filename: str):
    clip_path = config.JOBS_DIR / job_id / clip_filename
    if not clip_path.exists():
        raise HTTPException(status_code=404, detail="Requested clip file not found")
    return FileResponse(
        path=str(clip_path),
        media_type="video/mp4",
        filename=clip_filename
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=config.PORT, reload=False)
