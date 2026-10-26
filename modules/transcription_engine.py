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

import time

logger = logging.getLogger("al-haqq-engine.transcription")

class TranscriptionEngine:
    def __init__(self):
        self.primary_key = config.GROQ_API_KEY
        self.fallback_key = config.GROQ_API_KEY_FALLBACK
        self.model = config.GROQ_WHISPER_MODEL
        self._key_cooldown: Dict[str, float] = {}

    def _call_groq_whisper(self, api_key: str, audio_path: Path):
        client = Groq(api_key=api_key, timeout=120.0)
        with open(audio_path, "rb") as f:
            return client.audio.transcriptions.create(
                file=(audio_path.name, f),
                model=self.model,
                language="ur",
                response_format="verbose_json"
            )

    def transcribe(self, audio_path: Path, cache_path: Path = None) -> Dict[str, Any]:
        """
        Transcribes speech using Groq Whisper Large-v3 with cooldown failover and retry backoff.
        Returns full text and word/phrase segments with timestamps.
        """
        if cache_path and cache_path.exists():
            logger.info(f"Loading cached transcript from {cache_path}")
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not read cache {cache_path}: {e}, re-transcribing...")

        logger.info(f"Transcribing {audio_path.name} via Groq ({self.model})...")
        
        now = time.time()
        keys_to_try = []
        if self.primary_key and self._key_cooldown.get(self.primary_key, 0) < now:
            keys_to_try.append(("primary", self.primary_key))
        if self.fallback_key and self._key_cooldown.get(self.fallback_key, 0) < now:
            keys_to_try.append(("fallback", self.fallback_key))

        # If both are cooled down, force trying both anyway
        if not keys_to_try:
            if self.primary_key:
                keys_to_try.append(("primary", self.primary_key))
            if self.fallback_key:
                keys_to_try.append(("fallback", self.fallback_key))

        if not keys_to_try:
            raise ValueError("No GROQ_API_KEY is configured")

        res = None
        last_err = None
        for key_label, key_val in keys_to_try:
            # Try up to 2 attempts per key with backoff for rate limits
            for attempt in range(2):
                try:
                    logger.info(f"Attempting Whisper transcription with {key_label} key (attempt {attempt+1})...")
                    res = self._call_groq_whisper(key_val, audio_path)
                    logger.info(f"Whisper transcription succeeded with {key_label} key!")
                    break
                except Exception as e:
                    last_err = e
                    err_str = str(e).lower()
                    if "rate_limit" in err_str or "429" in err_str or "quota" in err_str:
                        backoff = 15.0 * (attempt + 1)
                        logger.warning(f"Groq {key_label} key rate-limited. Waiting {backoff:.0f}s backoff before retry...")
                        time.sleep(backoff)
                        self._key_cooldown[key_val] = time.time() + 60.0
                    else:
                        logger.warning(f"Groq {key_label} key failed: {e}")
                        break
            if res is not None:
                break

        if res is None:
            raise RuntimeError(f"All Groq Whisper keys failed: {last_err}") from last_err

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
            
            # Transcribe individual chunk with guaranteed local disk cache
            chunk_cache_path = chunk_path.with_suffix(".transcript.json")
            chunk_res = self.transcribe(audio_path=chunk_path, cache_path=chunk_cache_path)
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
