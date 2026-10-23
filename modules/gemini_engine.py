"""
modules/gemini_engine.py
Topic classification, Roman Urdu hook generation, and subtitle translation using Gemini Flash Lite with Groq fallback.
"""

import json
import logging
import time
from typing import List, Dict, Any
from groq import Groq
import google.generativeai as genai
import config

logger = logging.getLogger("al-haqq-engine.gemini")

class GeminiEngine:
    def __init__(self):
        self.api_key = config.GEMINI_API_KEY
        self.primary_model = config.GEMINI_PRIMARY_MODEL
        self.groq_api_key = config.GROQ_API_KEY
        self.groq_fallback_llm = config.GROQ_FALLBACK_LLM

    def extract_topics(self, transcript_data: Dict[str, Any], max_clips: int = 5, offset_sec: float = 120.0) -> List[Dict[str, Any]]:
        """
        Parses full transcript, classifies topics into Shorts (< 3 mins) or Mini-Long (3-6 mins max),
        and generates hooks, Arabic citations, and English subtitle translations.
        """
        segments = transcript_data.get("segments", [])
        if not segments:
            raise ValueError("Transcript segments are empty!")

        # Format transcript segments with timestamp markers
        lines = []
        for s in segments:
            start = s.get("start", 0) + offset_sec
            end = s.get("end", 0) + offset_sec
            text = s.get("text", "").strip()
            lines.append(f"[{start:.1f}s - {end:.1f}s]: {text}")

        transcript_context = "\n".join(lines[:250]) # Analyze first 250 segments

        prompt = f"""
Aap ek senior Islamic editor aur YouTube content strategist hain jo Mufti Tariq Masood ke bayanat se high-value reels aur shorts extract karte hain.

Bayan ke transcript segments timestamps ke sath:
\"\"\"
{transcript_context}
\"\"\"

### STRICT RULES:
1. "Mukammal Baat": Kisi bhi clip me baat aadhi nahi karni. Sawal ya topic jahan se shuru hota hai wahan se start ho, aur jahan Mufti sahab ka hukum/jawab/naseehat 100% poori hoti hai wahan end ho. Adhuri baat sakhti se mana hai.
2. "Focus & Duration":
   - PRIMARY FOCUS SHORTS PAR HAI: Duration must be between 45s and 175s (< 3 minutes).
   - AGAR TOPIC BOHOT AHEM HAI AUR TAFSEEL ZAROORI HAI: To use "mini_long" category do (Duration must be between 180s and 360s, STRICT MAX 6 MINUTES). 6 minutes se lambi video nahi banani.
3. Roman Urdu Hook: Template ke upar Twitter/X style question likhna hai (under 90 chars, Roman Urdu me, jaisa: 'Dil jab galat cheezein sune to kya hota hai?').
4. Subtitles (Arabic + English):
   - "arabic_sub": Agar us clip me koi Quran ki Ayat ya Hadees mubarak quote hui hai to uska sahi Arabic text, warna topic ka concise Arabic keyword.
   - "english_sub": Clip ki markazi baat ya Ayat/Hadees ka clean English translation (1 line, 10-15 words max).

Mujhe maximum {max_clips} best clips nikaal kar do.
Output STRICTLY valid JSON ONLY (Array of objects), no markdown code blocks:
[
  {{
    "start_time": 150.0,
    "end_time": 210.0,
    "category": "shorts",
    "roman_urdu_hook": "...",
    "arabic_sub": "...",
    "english_sub": "...",
    "yt_title": "...",
    "yt_description": "...",
    "tags": ["#Shorts", "#MuftiTariqMasood", "#IslamicReminder"]
  }}
]
"""
        raw_text = None
        # 1. Try Gemini Models
        genai.configure(api_key=self.api_key)
        for model_name in [self.primary_model, "gemini-2.0-flash", "gemini-1.5-flash"]:
            try:
                logger.info(f"Calling Gemini ({model_name})...")
                model = genai.GenerativeModel(model_name)
                res = model.generate_content(prompt)
                raw_text = res.text.strip()
                logger.info(f"Successfully generated topics with {model_name}!")
                break
            except Exception as e:
                logger.warning(f"{model_name} failed: {e}. Retrying with next...")
                time.sleep(2)

        # 2. Fallback to Groq LLM
        if not raw_text and self.groq_api_key:
            logger.info(f"Falling back to Groq LLM ({self.groq_fallback_llm})...")
            groq_client = Groq(api_key=self.groq_api_key)
            completion = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.groq_fallback_llm
            )
            raw_text = completion.choices[0].message.content.strip()
            logger.info("Successfully generated topics with Groq LLM fallback!")

        if not raw_text:
            raise RuntimeError("All AI models failed to generate topics!")

        # Clean JSON markdown fences
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

        clips_data = json.loads(raw_text)
        logger.info(f"Successfully extracted {len(clips_data)} high-retention clips!")
        return clips_data
