"""
modules/transcription_engine.py
Groq Whisper Large-v3 client with primary/fallback key rotation and segment caching.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any
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
        client = Groq(api_key=self.primary_key)
        try:
            with open(audio_path, "rb") as f:
                res = client.audio.transcriptions.create(
                    file=(audio_path.name, f),
                    model=self.model,
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
                    response_format="verbose_json"
                )

        data = {
            "text": res.text,
            "segments": res.segments
        }

        if cache_path:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Transcript cached to {cache_path}")

        logger.info(f"Transcription complete! Length: {len(res.text)} characters.")
        return data
