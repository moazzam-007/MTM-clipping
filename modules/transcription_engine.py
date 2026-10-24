"""
modules/transcription_engine.py
Groq Whisper Large-v3 client with primary/fallback key rotation and segment caching.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from groq import Groq
import config

logger = logging.getLogger("al-haqq-engine.transcription")

class TranscriptionEngine:
    def __init__(self):
        self.primary_key = config.GROQ_API_KEY
        self.fallback_key = config.GROQ_API_KEY_FALLBACK
        self.model = config.GROQ_WHISPER_MODEL

    def transcribe(self, audio_path: Path, cache_path: Path = None) -> Dict[str, Any]:
        """
        Transcribes speech using Groq Whisper Large-v3.
        Returns full text and word/phrase segments with timestamps.
        """
        if cache_path and cache_path.exists():
            logger.info(f"Loading cached transcript from {cache_path}")
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)

        logger.info(f"Transcribing {audio_path.name} via Groq ({self.model})...")
        
        # 1. Try Primary Groq Key
        res = None
        try:
            if not self.primary_key:
                raise ValueError("GROQ_API_KEY is not configured")
            client = Groq(api_key=self.primary_key)
            with open(audio_path, "rb") as f:
                res = client.audio.transcriptions.create(
                    file=(audio_path.name, f),
                    model=self.model,
                    language="ur",
                    response_format="verbose_json"
                )
        except Exception as e:
            logger.warning(f"Primary Groq key error: {e}. Attempting fallback key...")
            if not self.fallback_key:
                raise RuntimeError("Primary Groq key failed and no fallback key provided!") from e
            client = Groq(api_key=self.fallback_key)
            with open(audio_path, "rb") as f:
                res = client.audio.transcriptions.create(
                    file=(audio_path.name, f),
                    model=self.model,
                    language="ur",
                    response_format="verbose_json"
                )

        # Normalize segments into dicts
        raw_segments = getattr(res, "segments", []) or []
        clean_segments = []
        for s in raw_segments:
            if isinstance(s, dict):
                clean_segments.append(s)
            elif hasattr(s, "model_dump"):
                clean_segments.append(s.model_dump())
            elif hasattr(s, "__dict__"):
                clean_segments.append(s.__dict__)
            else:
                clean_segments.append(dict(s))

        data = {
            "text": getattr(res, "text", ""),
            "segments": clean_segments
        }

        if cache_path:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Transcript cached to {cache_path}")

        logger.info(f"Transcription complete! Length: {len(data['text'])} characters.")
        return data

    def transcribe_chunks(self, chunks: List[Dict[str, Any]], cache_path: Path = None) -> Dict[str, Any]:
        """
        Transcribes multiple sequential audio chunks and merges their word/phrase segments
        into a single global timeline. Guarantees continuous timestamps across full bayanat (60-120 mins).
        """
        if cache_path and cache_path.exists():
            logger.info(f"Loading cached full transcript from {cache_path}")
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)

        logger.info(f"Beginning multi-chunk transcription for {len(chunks)} audio segments...")
        all_segments = []
        full_text_parts = []

        for chunk in chunks:
            chunk_path = Path(chunk["path"])
            offset = float(chunk["start_offset"])
            logger.info(f"Processing chunk {chunk.get('index', 0)} (offset {offset:.1f}s)...")
            
            # Transcribe individual chunk
            chunk_res = self.transcribe(audio_path=chunk_path)
            chunk_text = chunk_res.get("text", "").strip()
            if chunk_text:
                full_text_parts.append(chunk_text)

            # Offset segment boundaries to global video timeline
            for s in chunk_res.get("segments", []):
                raw_start = float(s.get("start", 0.0))
                raw_end = float(s.get("end", 0.0))
                text = str(s.get("text", "")).strip()
                if not text:
                    continue
                all_segments.append({
                    "start": round(raw_start + offset, 2),
                    "end": round(raw_end + offset, 2),
                    "text": text
                })

        master_data = {
            "text": " ".join(full_text_parts),
            "segments": all_segments
        }

        if cache_path:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(master_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Aggregated transcript cached to {cache_path} ({len(all_segments)} total segments).")

        return master_data
