"""
modules/youtube_engine.py
Handles YouTube stream URL resolution, lightweight audio extraction, and fast HD video clipping.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger("al-haqq-engine.youtube")

class YouTubeEngine:
    @staticmethod
    def get_video_info(video_url: str) -> Dict[str, Any]:
        """
        Fetches YouTube metadata and direct playable stream URL using yt-dlp with Node JS runtime.
        """
        logger.info(f"Resolving video info and stream for: {video_url}")
        
        # 1. Fetch metadata
        meta_cmd = [
            "yt-dlp",
            "--js-runtimes", "node",
            "--dump-json",
            "--no-playlist",
            video_url
        ]
        try:
            meta_out = subprocess.check_output(meta_cmd, text=True, stderr=subprocess.DEVNULL)
            meta = json.loads(meta_out)
        except Exception as e:
            logger.warning(f"Full JSON dump failed ({e}), falling back to basic metadata...")
            basic_cmd = ["yt-dlp", "--print", "%(id)s||%(title)s||%(duration)s", video_url]
            basic_out = subprocess.check_output(basic_cmd, text=True).strip().split("||")
            meta = {
                "id": basic_out[0],
                "title": basic_out[1] if len(basic_out) > 1 else "Unknown Video",
                "duration": float(basic_out[2]) if len(basic_out) > 2 and basic_out[2].isdigit() else 3600
            }

        # 2. Fetch direct stream URL via android client (stable, no 403)
        stream_cmd = [
            "yt-dlp",
            "--js-runtimes", "node",
            "--extractor-args", "youtube:player_client=android",
            "-f", "18/best[height<=720]/best",
            "-g",
            video_url
        ]
        stream_out = subprocess.check_output(stream_cmd, text=True).strip().splitlines()
        stream_url = stream_out[-1]
        
        return {
            "video_id": meta.get("id"),
            "title": meta.get("title"),
            "duration": float(meta.get("duration", 0)),
            "stream_url": stream_url
        }

    @staticmethod
    def extract_audio(stream_url: str, output_path: Path, start_sec: int = 120, duration_sec: int = 1200) -> Path:
        """
        Streams audio directly via FFmpeg and encodes to 32kbps 16kHz mono MP3.
        Keeps file size very small (<10MB) for Groq Whisper limits.
        """
        logger.info(f"Streaming {duration_sec}s of audio to {output_path}...")
        ff_cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-t", str(duration_sec),
            "-i", stream_url,
            "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k",
            str(output_path)
        ]
        subprocess.check_call(ff_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info(f"Audio stream extracted successfully ({output_path.stat().st_size / 1024:.1f} KB)")
        return output_path

    @staticmethod
    def cut_hd_clip(stream_url: str, start_sec: float, duration_sec: float, output_path: Path) -> Path:
        """
        Fast-seeks into the YouTube stream and cuts the exact segment into progressive 25fps MP4.
        """
        logger.info(f"Cutting HD clip ({duration_sec:.1f}s from {start_sec:.1f}s) to {output_path}...")
        ff_cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-i", stream_url,
            "-t", str(duration_sec),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            str(output_path)
        ]
        subprocess.check_call(ff_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info(f"HD clip saved successfully ({output_path.stat().st_size / (1024*1024):.2f} MB)")
        return output_path
