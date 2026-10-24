"""
modules/youtube_engine.py
Handles YouTube stream resolution, audio streaming, and robust 720p clip cutting with network reconnects.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger("al-haqq-engine.youtube")

class YouTubeEngine:
    @staticmethod
    def get_video_info(video_url: str) -> Dict[str, Any]:
        """
        Fetches YouTube metadata and direct playable stream URL using yt-dlp with Node.js runtime.
        """
        logger.info(f"Resolving video info and stream for: {video_url}")
        
        # 1. Fetch metadata with --no-playlist
        meta_cmd = [
            "yt-dlp",
            "--js-runtimes", "node",
            "--no-playlist",
            "--dump-json",
            video_url
        ]
        try:
            res = subprocess.run(meta_cmd, capture_output=True, text=True, timeout=45, check=True)
            meta = json.loads(res.stdout)
        except Exception as e:
            logger.warning(f"Full JSON dump failed ({e}), falling back to basic metadata...")
            basic_cmd = [
                "yt-dlp",
                "--js-runtimes", "node",
                "--no-playlist",
                "--max-downloads", "1",
                "--print", "%(id)s||%(title)s||%(duration)s",
                video_url
            ]
            basic_res = subprocess.run(basic_cmd, capture_output=True, text=True, timeout=30, check=True)
            parts = basic_res.stdout.strip().splitlines()[-1].split("||")
            dur = 3600.0
            try:
                dur = float(parts[2]) if len(parts) > 2 else 3600.0
            except ValueError:
                dur = 3600.0
            meta = {
                "id": parts[0],
                "title": parts[1] if len(parts) > 1 else "Mufti Tariq Masood Bayan",
                "duration": dur
            }

        # 2. Fetch direct stream URL (prioritize 720p adaptive stream, fallback 22, then 18)
        stream_cmd = [
            "yt-dlp",
            "--js-runtimes", "node",
            "--no-playlist",
            "--extractor-args", "youtube:player_client=android",
            "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]/22/18/best",
            "-g",
            video_url
        ]
        stream_res = subprocess.run(stream_cmd, capture_output=True, text=True, timeout=45, check=True)
        lines = [line.strip() for line in stream_res.stdout.strip().splitlines() if line.strip().startswith("http")]
        video_stream = lines[0] if lines else ""
        audio_stream = lines[1] if len(lines) > 1 else ""

        raw_dur = meta.get("duration")
        try:
            dur_val = float(raw_dur) if raw_dur is not None else 0.0
        except (ValueError, TypeError):
            dur_val = 0.0

        return {
            "video_id": meta.get("id"),
            "title": meta.get("title"),
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
            res = subprocess.run(ff_cmd, capture_output=True, text=True, timeout=180)
            if res.returncode != 0:
                logger.error(f"FFmpeg chunk extraction failed for chunk {chunk_index}: {res.stderr[-300:]}")
                raise RuntimeError(f"FFmpeg audio chunk extraction failed: {res.stderr[-150:]}")
                
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

        res = subprocess.run(ff_cmd, capture_output=True, text=True, timeout=120)
        if res.returncode != 0:
            logger.error(f"FFmpeg video cutting failed: {res.stderr[-400:]}")
            raise RuntimeError(f"FFmpeg video cutting failed: {res.stderr[-200:]}")

        logger.info(f"HD clip saved successfully ({output_path.stat().st_size / (1024*1024):.2f} MB)")
        return output_path
