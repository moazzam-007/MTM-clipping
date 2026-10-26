"""
modules/gemini_engine.py
Topic classification, Roman Urdu hook generation, and subtitle translation using Gemini Flash Lite with Groq fallback.
Handles full-lecture transcripts (60-120 mins) with strict "Mukammal Baat" and YouTube SEO tag logic.
"""

import re
import json
import logging
import time
from typing import List, Dict, Any, Optional
from groq import Groq
import config

logger = logging.getLogger("al-haqq-engine.gemini")

GEMINI_PROMPT_TEMPLATE = """Aap ek senior Islamic editor aur YouTube content strategist hain jo Mufti Tariq Masood ke bayanat se high-value reels, shorts, aur mini-long clips extract karte hain ("Al Haqq" channel ke liye).

Bayan ke transcript segments timestamps ke sath:
\"\"\"
{{TRANSCRIPT_CONTEXT}}
\"\"\"

### STRICT RULES:
1. "Mukammal Baat" (Non-Negotiable):
   Kisi bhi clip me baat adhoori nahi honi chahiye. Sawal ya topic jahan se shuru hota hai clip wahan se start ho, aur jahan Mufti sahab ka jawab/hukum/naseehat 100% poori hoti hai wahan end ho. Adhoori baat sakhti se mana hai.

2. "Controversial & Hot Topics Allowed":
   Controversial ya hot debate wale sawalaat, talaq/nikah, aapas ke social masail, ya shari rulings bilkul skip NA karein (ye hamare channel ke liye high priority aur mufeed hain).
   Sirf aur sirf shuruat ka khutbah (Bismillah, Hamd-o-Sana), formal salam/intro, aur Chanda appeals ko skip karein.

3. "Focus & Duration":
   - PRIMARY FOCUS SHORTS PAR HAI: "shorts" category duration 35s se 175s ke darmiyan honi chahiye (< 3 minutes).
   - AGAR TOPIC BOHOT AHEM HAI AUR TAFSEEL ZAROORI HAI: To "mini_long" category dein (duration 180s se 360s, STRICT MAX 6 MINUTES). 6 minutes se lambi video nahi banani.

4. "YouTube SEO & #Shorts Logic":
   - Agar category "shorts" hai: To "yt_title" ke aakhir me aur "tags" me "#Shorts" ZAROOR shamil karein.
   - Agar category "mini_long" hai: To "yt_title" aur "tags" me "#Shorts" KABHI BHI NAHI lagana chahiye (kyunki YouTube par 3 minute se badi video Short nahi hoti). Iski jagah #MuftiTariqMasood, #IslamicLecture, #Bayan use karein.

5. "Verification Words":
   Har clip ke transcript ke pehle 5-6 alfaaz ("first_words") aur aakhri 5-6 alfaaz ("last_words") exact transcript ke mutabiq likhein taake timestamp boundary verify ho sake.

6. "Roman Urdu Hook":
   Template ke top headline ke liye Twitter/X style punchy question ya statement likhein (under 90 chars, Roman Urdu me, jaise: 'Namaz me galti ho jaye to sajda sahw kab karein?').

7. "Subtitles (Arabic + English)":
   - "arabic_sub": Agar Mufti sahab ne us clip me koi Quran ki Ayat ya Hadith mubarak tilawat ki hai to uska sahi Arabic text (under 85 chars). Agar Ayat/Hadith tilawat nahi ki to topic ka concise Arabic keyword (jaise: 'الصَّبْرُ عِنْدَ الْمَصَائِبِ').
   - "arabic_source": Quran ki ayat ho to "quran", Hadith ho to "hadees", keyword ho to "keyword".
   - "reference": Ayat ka Surah:Ayah ya Hadith ki kitab (jaise "Al-Baqarah: 153" ya "Sahih Bukhari: 1224"). Agar keyword hai to empty string "" rakhein.
   - "english_sub": Clip ki markazi baat ya Ayat/Hadith ka clean English translation (1 line, 10-14 words max).

Mujhe maximum {{MAX_CLIPS}} best clips nikaal kar dein.
Output STRICTLY valid JSON ONLY (Array of objects):
[
  {
    "start_time": 150.0,
    "end_time": 210.0,
    "category": "shorts",
    "first_words": "Agar koi shakhs namaz me",
    "last_words": "to uski namaz mukammal hogi",
    "roman_urdu_hook": "Namaz me galti ho jaye to sajda sahw kab karein?",
    "arabic_sub": "فَسَجَدَ سَجْدَتَيْنِ قَبْلَ أَنْ يُسَلِّمَ",
    "arabic_source": "hadees",
    "reference": "Sahih Bukhari: 1224",
    "english_sub": "He performed two prostrations before completing the prayer",
    "yt_title": "Sajda Sahw Ka Sahi Tareeqa | Mufti Tariq Masood #Shorts",
    "yt_description": "Mufti Tariq Masood explains the correct method of Sajda Sahw in prayer. Watch full clip for complete guidance.",
    "tags": ["#Shorts", "#MuftiTariqMasood", "#Namaz", "#IslamicRuling"]
  }
]
"""

class GeminiEngine:
    def __init__(self):
        self.api_key = config.GEMINI_API_KEY
        self.primary_model = config.GEMINI_PRIMARY_MODEL
        self.groq_api_key = config.GROQ_API_KEY
        self.groq_fallback_llm = config.GROQ_FALLBACK_LLM

    def extract_topics(self, transcript_data: Dict[str, Any], max_clips: int = 8, offset_sec: float = 0.0) -> List[Dict[str, Any]]:
        """
        Parses full transcript, classifies topics into Shorts (< 3 mins) or Mini-Long (3-6 mins max),
        generates hooks, Arabic citations, English subtitle translations, and applies audio padding.
        """
        segments = transcript_data.get("segments", [])
        if not segments:
            raise ValueError("Transcript segments are empty!")

        lines = []
        for s in segments:
            start = float(s.get("start", 0)) + offset_sec
            end = float(s.get("end", 0)) + offset_sec
            text = str(s.get("text", "")).strip()
            if text:
                lines.append(f"[{start:.1f}s - {end:.1f}s]: {text}")

        transcript_context = "\n".join(lines)

        # Safe placeholder replacement to prevent Python .format() / f-string KeyError with JSON braces
        prompt = GEMINI_PROMPT_TEMPLATE.replace("{{MAX_CLIPS}}", str(max_clips)).replace("{{TRANSCRIPT_CONTEXT}}", transcript_context)

        raw_text = None
        # 1. Try modern google-genai SDK with stable models and temperature 0.3
        try:
            from google import genai as modern_genai
            from google.genai import types as genai_types
            if self.api_key:
                client = modern_genai.Client(api_key=self.api_key)
                for model_name in [self.primary_model, "gemini-2.5-flash-lite", "gemini-1.5-flash", "gemini-2.0-flash"]:
                    try:
                        logger.info(f"Calling Google GenAI ({model_name}) with temperature=0.3...")
                        config_obj = genai_types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.3
                        )
                        res = client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config=config_obj
                        )
                        raw_text = res.text.strip()
                        logger.info(f"Successfully generated topics with {model_name}!")
                        break
                    except Exception as m_err:
                        logger.warning(f"Model {model_name} failed: {m_err}. Trying next...")
        except Exception as sdk_err:
            logger.warning(f"Modern google-genai SDK failed: {sdk_err}")

        # 2. Fallback to Groq LLM (with safe prompt truncation to prevent 12k TPM rate-limiting)
        if not raw_text and self.groq_api_key:
            logger.info(f"Falling back to Groq LLM ({self.groq_fallback_llm})...")
            try:
                groq_prompt = prompt
                # Truncate transcript context if prompt exceeds 10k tokens (~35k chars) for Groq free tier
                if len(groq_prompt) > 35000:
                    logger.info("Truncating transcript context for Groq TPM guard...")
                    groq_prompt = GEMINI_PROMPT_TEMPLATE.replace("{{MAX_CLIPS}}", str(max_clips)).replace("{{TRANSCRIPT_CONTEXT}}", transcript_context[:32000])

                groq_client = Groq(api_key=self.groq_api_key)
                completion = groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": groq_prompt}],
                    model=self.groq_fallback_llm,
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                raw_text = completion.choices[0].message.content.strip()
                logger.info("Successfully generated topics with Groq LLM fallback!")
            except Exception as g_err:
                logger.error(f"Groq fallback failed: {g_err}")

        if not raw_text:
            raise RuntimeError("All AI models failed to generate topics!")

        # Safe and robust JSON extraction (handles code fences, truncated buffers, and object wrappers)
        clips_raw = self._safe_parse_json(raw_text)

        # Directional boundary snapping: start snaps at or slightly before target (within 6s), end snaps at or slightly after target (within 6s)
        starts = sorted(float(s.get("start", 0.0)) + offset_sec for s in segments) if segments else []
        ends = sorted(float(s.get("end", 0.0)) + offset_sec for s in segments) if segments else []

        def _snap_start(t: float, max_back: float = 6.0) -> float:
            if not starts:
                return round(t, 1)
            c = [x for x in starts if x <= t + 0.2]
            if c and (t - max(c)) <= max_back:
                return round(max(c), 1)
            return round(t, 1)

        def _snap_end(t: float, max_fwd: float = 6.0) -> float:
            if not ends:
                return round(t, 1)
            c = [x for x in ends if x >= t - 0.2]
            if c and (min(c) - t) <= max_fwd:
                return round(min(c), 1)
            return round(t, 1)

        # Post-validate, sanitize, snap to Whisper boundaries, apply audio padding, and enforce YouTube SEO tags
        valid_clips = []
        for c in clips_raw:
            if not isinstance(c, dict):
                continue
            try:
                raw_s = float(c.get("start_time", 0))
                raw_e = float(c.get("end_time", 0))
                
                if raw_s < 0 or raw_e <= raw_s:
                    continue

                # Directional boundary snap: guarantees sentences are not cut off midway
                snapped_s = _snap_start(raw_s)
                snapped_e = _snap_end(raw_e)
                
                # Audio padding: 0.3s start lead-in and 0.5s end tail for seamless audio
                padded_start = max(0.0, round(snapped_s - 0.3, 1))
                padded_end = round(snapped_e + 0.5, 1)
                dur = round(padded_end - padded_start, 1)

                if dur >= config.SHORTS_MIN_DURATION and dur <= config.MINI_LONG_MAX_DURATION:
                    # If core duration was under 175s, strictly treat as shorts
                    core_dur = snapped_e - snapped_s
                    cat = "shorts" if core_dur <= config.SHORTS_MAX_DURATION else "mini_long"
                    
                    # Enforce strict YouTube algorithm rule for #Shorts tag without truncation
                    yt_title = str(c.get("yt_title", "")).strip()
                    raw_tags = c.get("tags", [])
                    if isinstance(raw_tags, list):
                        tags = [str(t).strip() for t in raw_tags if str(t).strip()]
                    else:
                        tags = ["#MuftiTariqMasood"]

                    if cat == "shorts":
                        if "#Shorts" not in yt_title and "#shorts" not in yt_title.lower():
                            yt_title = f"{yt_title[:90].strip()} #Shorts"
                        else:
                            yt_title = yt_title[:100]
                        if "#Shorts" not in tags and "#shorts" not in [t.lower() for t in tags]:
                            tags.insert(0, "#Shorts")
                    else:
                        # mini_long: strictly remove #Shorts from title and tags
                        yt_title = re.sub(r'#shorts\b', '', yt_title, flags=re.IGNORECASE).strip()
                        tags = [t for t in tags if t.lower() != "#shorts"]
                        if "#MuftiTariqMasood" not in tags:
                            tags.insert(0, "#MuftiTariqMasood")

                    valid_clips.append({
                        "start_time": padded_start,
                        "end_time": padded_end,
                        "raw_start_time": round(raw_s, 1),
                        "raw_end_time": round(raw_e, 1),
                        "duration": dur,
                        "category": cat,
                        "first_words": str(c.get("first_words", "")).strip()[:80],
                        "last_words": str(c.get("last_words", "")).strip()[:80],
                        "roman_urdu_hook": str(c.get("roman_urdu_hook", "")).strip()[:100],
                        "arabic_sub": str(c.get("arabic_sub", "")).strip()[:120],
                        "arabic_source": str(c.get("arabic_source", "keyword")).strip()[:20],
                        "reference": str(c.get("reference", "")).strip()[:50],
                        "english_sub": str(c.get("english_sub", "")).strip()[:140],
                        "yt_title": yt_title,
                        "yt_description": str(c.get("yt_description", "")).strip()[:1000],
                        "tags": tags
                    })
                    
                    if len(valid_clips) >= max_clips:
                        break
            except (ValueError, TypeError) as parse_err:
                logger.warning(f"Skipping malformed topic: {parse_err}")

        logger.info(f"Successfully extracted, snapped, and sanitized {len(valid_clips)} valid clips!")
        return valid_clips

    @staticmethod
    def _safe_parse_json(raw_text: str) -> List[Dict[str, Any]]:
        """Safely parses JSON array or object from raw LLM output with multiple fallbacks."""
        cleaned = raw_text.strip()
        if "```" in cleaned:
            cleaned = re.sub(r'```(?:json)?\s*([\s\S]*?)\s*```', r'\1', cleaned).strip()

        # Try direct parse
        try:
            data = json.loads(cleaned)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for key in ("clips", "topics", "items", "data"):
                    if isinstance(data.get(key), list):
                        return data[key]
                for v in data.values():
                    if isinstance(v, list):
                        return v
        except json.JSONDecodeError:
            pass

        # Try bracket slice parse
        s_idx = cleaned.find('[')
        e_idx = cleaned.rfind(']')
        if s_idx != -1 and e_idx != -1 and e_idx > s_idx:
            try:
                arr = json.loads(cleaned[s_idx:e_idx + 1])
                if isinstance(arr, list):
                    return arr
            except json.JSONDecodeError:
                pass

        # Try object slice parse
        s_obj = cleaned.find('{')
        e_obj = cleaned.rfind('}')
        if s_obj != -1 and e_obj != -1 and e_obj > s_obj:
            try:
                obj = json.loads(cleaned[s_obj:e_obj + 1])
                if isinstance(obj, dict):
                    for key in ("clips", "topics", "items"):
                        if isinstance(obj.get(key), list):
                            return obj[key]
                    for v in obj.values():
                        if isinstance(v, list):
                            return v
            except json.JSONDecodeError:
                pass

        logger.error(f"Unparseable LLM output: {raw_text[:250]}")
        raise ValueError("Could not extract a valid JSON list of clips from LLM response")
