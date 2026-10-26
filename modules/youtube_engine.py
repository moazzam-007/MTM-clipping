"""
modules/youtube_engine.py
Handles YouTube stream resolution, audio streaming, and robust 720p clip cutting with network reconnects.
"""

import os
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List

from modules.safe_url import canonical_youtube_url

logger = logging.getLogger("al-haqq-engine.youtube")

class YouTubeEngine:
    @staticmethod
    def get_video_info(video_url: str) -> Dict[str, Any]:
        """
        Fetches YouTube metadata and direct playable stream URL using yt-dlp with Node.js runtime.
        Guarded with canonical URL validation and argument injection protections.
        """
        clean_url = canonical_youtube_url(video_url)
        logger.info(f"Resolving video info and stream for: {clean_url}")
        
        # Check for cookies in Environment Variable (Secure) or local file
        cookie_file = None
        env_cookies = os.environ.get("YOUTUBE_COOKIES_TXT") or os.environ.get("YOUTUBE_COOKIES_BASE64")
        if env_cookies:
            try:
                import tempfile
                import base64
                if not env_cookies.startswith("# Netscape"):
                    cookie_content = base64.b64decode(env_cookies).decode("utf-8")
                else:
                    cookie_content = env_cookies
                temp_cookie = Path(tempfile.gettempdir()) / "yt_runtime_cookies.txt"
                temp_cookie.write_text(cookie_content, encoding="utf-8")
                cookie_file = temp_cookie
                logger.info("Using secure runtime cookies from environment variable")
            except Exception as e:
                logger.warning(f"Failed to parse cookies from env: {e}")
        
        if not cookie_file:
            cookie_file = next((p for p in [
                Path("cookies.txt"),
                Path(__file__).parent.parent / "cookies.txt",
                Path("/app/cookies.txt")
            ] if p.exists() and p.stat().st_size > 50), None)

        cookie_args = ["--cookies", str(cookie_file)] if cookie_file else ["--extractor-args", "youtube:player_client=android,ios,mweb"]
        logger.info(f"Using cookies: {cookie_file is not None} for stream resolution")

        # Preferred format: 720p H.264 (avc1) + AAC (m4a) to avoid heavy AV1 CPU decoding on Render 0.1 CPU
        fmt = "bestvideo[height<=720][vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/best"

        cmd = [
            "yt-dlp",
            "--ignore-config",
            "--js-runtimes", "node",
            "--no-playlist",
            *cookie_args,
            "-f", fmt,
            "--dump-single-json",
            "--",
            clean_url
        ]

        logger.info("Executing unified yt-dlp metadata and stream resolution...")
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired:
            logger.error("yt-dlp command timed out after 90s")
            raise RuntimeError("yt-dlp stream resolution timed out after 90 seconds")

        meta = None
        if res.returncode == 0 and res.stdout.strip():
            try:
                meta = json.loads(res.stdout)
            except Exception as parse_err:
                logger.warning(f"Failed to parse yt-dlp JSON: {parse_err}")

        # Fallback format if primary 720p adaptive fails (e.g. video only has pre-muxed 360p or direct stream)
        if not meta or not meta.get("url") and not meta.get("requested_formats"):
            logger.warning(f"Primary format resolution failed (code {res.returncode}): {res.stderr[-400:] if res.stderr else 'no output'}. Retrying with combined fallback...")
            fallback_cmd = [
                "yt-dlp",
                "--ignore-config",
                "--js-runtimes", "node",
                "--no-playlist",
                "--extractor-args", "youtube:player_client=android,ios,mweb",
                "-f", "best[height<=720]/b/ba[ext=m4a]/ba",
                "--dump-single-json",
                "--",
                clean_url
            ]
            try:
                fb_res = subprocess.run(fallback_cmd, capture_output=True, text=True, timeout=90)
                if fb_res.returncode == 0 and fb_res.stdout.strip():
                    meta = json.loads(fb_res.stdout)
                else:
                    err_msg = fb_res.stderr[-600:] if fb_res.stderr else f"Exit code {fb_res.returncode}"
                    logger.error(f"Fallback yt-dlp resolution also failed: {err_msg}")
                    raise RuntimeError(f"yt-dlp extraction failed: {err_msg}")
            except subprocess.TimeoutExpired:
                raise RuntimeError("yt-dlp fallback resolution timed out after 90s")

        # Extract direct stream URLs from requested_formats (dual stream) or single format
        video_stream = ""
        audio_stream = ""
        req_formats = meta.get("requested_formats")
        if req_formats and isinstance(req_formats, list) and len(req_formats) >= 2:
            video_stream = req_formats[0].get("url", "")
            audio_stream = req_formats[1].get("url", "")
        elif req_formats and isinstance(req_formats, list) and len(req_formats) == 1:
            video_stream = req_formats[0].get("url", "")
            audio_stream = ""
        else:
            video_stream = meta.get("url", "")
            audio_stream = ""

        # Validate video duration and metadata
        raw_dur = meta.get("duration")
        try:
            dur_val = float(raw_dur) if raw_dur is not None else 0.0
        except (ValueError, TypeError):
            dur_val = 0.0

        v_id = meta.get("id") or "unknown"
        v_title = meta.get("title") or "YouTube Video"

        logger.info(f"Resolved video: '{v_title}' ({dur_val}s) - Has video: {bool(video_stream)}, Has separate audio: {bool(audio_stream)}")

        return {
            "video_id": v_id,
            "title": v_title,
            "duration": dur_val,
            "stream_url": video_stream,
            "audio_stream_url": audio_stream
        }

    @staticmethod
    def extract_audio(stream_url: str, output_path: Path, start_sec: int = 0, duration_sec: int = 1200) -> Path:
        """
        Streams audio directly via FFmpeg with reconnect flags and encodes to 32kbps 16kHz mono MP3.
        """
        logger.info(f"Streaming {duration_sec}s of audio to {output_path}...")
        ff_cmd = [
            "ffmpeg", "-y",
            "-nostdin", "-loglevel", "error",
            "-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
            "-ss", str(start_sec),
            "-i", stream_url,
            "-t", str(duration_sec),
            "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k",
            str(output_path)
        ]
        res = subprocess.run(ff_cmd, capture_output=True, text=True, timeout=180)
        if res.returncode != 0:
            logger.error(f"FFmpeg audio extraction failed: {res.stderr[-400:]}")
            raise RuntimeError(f"FFmpeg audio extraction failed: {res.stderr[-200:]}")

        logger.info(f"Audio stream extracted successfully ({output_path.stat().st_size / 1024:.1f} KB)")
        return output_path

    @staticmethod
    def extract_audio_chunks(
        stream_url: str,
        output_dir: Path,
        total_duration_sec: float,
        start_sec: int = 0,
        chunk_duration_sec: int = 1200,
        max_duration_sec: int = 7200
    ) -> List[Dict[str, Any]]:
        """
        Splits full lecture audio into 20-minute (1200s) MP3 chunks at 32kbps 16kHz mono.
        Each chunk is ~4.8 MB, strictly within Groq's 25MB upload limit.
        Returns list of chunks with local path and absolute timestamp offset.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        effective_duration = min(float(total_duration_sec), float(max_duration_sec))
        
        current_offset = float(start_sec)
        end_boundary = effective_duration
        
        chunks = []
        chunk_index = 0
        
        while current_offset < end_boundary:
            remaining = end_boundary - current_offset
            this_chunk_dur = min(float(chunk_duration_sec), remaining)
            
            # Avoid extracting a tiny trailing stub (< 30s)
            if this_chunk_dur < 30.0 and chunk_index > 0:
                break
                
            chunk_file = output_dir / f"audio_chunk_{chunk_index}.mp3"
            logger.info(f"Extracting audio chunk {chunk_index}: {this_chunk_dur:.1f}s from offset {current_offset:.1f}s -> {chunk_file.name}")
            
            ff_cmd = [
                "ffmpeg", "-y",
                "-nostdin", "-loglevel", "error",
                "-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
                "-ss", str(current_offset),
                "-i", stream_url,
                "-t", str(this_chunk_dur),
                "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k",
                str(chunk_file)
            ]
            try:
                res = subprocess.run(ff_cmd, capture_output=True, text=True, timeout=300)
                if res.returncode != 0:
                    logger.error(f"FFmpeg chunk extraction failed for chunk {chunk_index}: {res.stderr[-300:]}")
                    raise RuntimeError(f"FFmpeg audio chunk extraction failed: {res.stderr[-150:]}")
            except subprocess.TimeoutExpired:
                logger.error(f"FFmpeg chunk extraction timed out for chunk {chunk_index}")
                raise RuntimeError(f"FFmpeg audio chunk {chunk_index} timed out after 300 seconds")
                
            chunks.append({
                "index": chunk_index,
                "path": chunk_file,
                "start_offset": current_offset,
                "duration": this_chunk_dur
            })
            
            current_offset += this_chunk_dur
            chunk_index += 1
            
        logger.info(f"Successfully extracted {len(chunks)} audio chunks covering up to {current_offset:.1f}s.")
        return chunks

    @staticmethod
    def cut_hd_clip(
        stream_url: str,
        start_sec: float,
        duration_sec: float,
        output_path: Path,
        audio_stream_url: str = ""
    ) -> Path:
        """
        Fast-seeks into the YouTube stream and cuts the exact segment into progressive 25fps MP4 with reconnects.
        Handles both single muxed progressive streams and dual video+audio adaptive streams.
        """
        logger.info(f"Cutting HD clip ({duration_sec:.1f}s from {start_sec:.1f}s) to {output_path}...")
        
        if audio_stream_url:
            # Dual stream (separate video and audio feeds with explicit stream mapping)
            ff_cmd = [
                "ffmpeg", "-y",
                "-nostdin", "-loglevel", "error",
                "-threads", "1",
                "-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
                "-ss", str(start_sec),
                "-i", stream_url,
                "-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
                "-ss", str(start_sec),
                "-i", audio_stream_url,
                "-t", str(duration_sec),
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", "-b:a", "128k",
                "-pix_fmt", "yuv420p",
                "-shortest",
                str(output_path)
            ]
        else:
            # Single muxed stream (format 22 or 18)
            ff_cmd = [
                "ffmpeg", "-y",
                "-nostdin", "-loglevel", "error",
                "-threads", "1",
                "-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
                "-ss", str(start_sec),
                "-i", stream_url,
                "-t", str(duration_sec),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", "-b:a", "128k",
                "-pix_fmt", "yuv420p",
                str(output_path)
            ]

        # Dynamic timeout scaled to duration (at least 300s, or 8x duration on 0.1 CPU)
        cut_timeout = max(300, int(duration_sec * 8))
        try:
            res = subprocess.run(ff_cmd, capture_output=True, text=True, timeout=cut_timeout)
            if res.returncode != 0:
                logger.error(f"FFmpeg video cutting failed: {res.stderr[-400:]}")
                raise RuntimeError(f"FFmpeg video cutting failed: {res.stderr[-200:]}")
        except subprocess.TimeoutExpired:
            logger.error(f"FFmpeg video cutting timed out after {cut_timeout}s")
            raise RuntimeError(f"FFmpeg video cutting timed out after {cut_timeout} seconds")

        logger.info(f"HD clip saved successfully ({output_path.stat().st_size / (1024*1024):.2f} MB)")
        return output_path
