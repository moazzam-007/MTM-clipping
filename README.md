# Al Haqq YouTube Shorts & Mini-Long Video Engine (`@al__haqqq`)

Fully automated video repurposing service that monitors long Islamic lectures (Mufti Tariq Masood), transcribes with Whisper, extracts complete engaging topics using Gemini, and renders them onto the **Al Haqq Twitter-style vertical template** (`720x1280`) with **Arabic & English subtitles**.

---

## 🚀 Key Pipeline Features

1. **Lightweight YouTube Streamer (`modules/youtube_engine.py`)**:
   - Streams audio and cuts 720p HD clips directly from YouTube without downloading full multi-gigabyte videos.
   - Guarded with canonical URL validation and argument injection protections (`modules/safe_url.py`).

2. **Groq Whisper Large-v3 Speech-to-Text (`modules/transcription_engine.py`)**:
   - Ultra-fast transcription of Urdu speech with word/segment timestamps.
   - Dual Groq API key rotation with automatic cooldown failover.
   - Per-chunk disk persistence: already-transcribed audio chunks are never re-transcribed on retry.

3. **Gemini AI Topic Classifier (`modules/gemini_engine.py`)**:
   - **Zero "Adhuri Baat" Rule**: Identifies complete questions, rulings, and naseehat from start to finish.
   - **Whisper Boundary Snapping**: proposed start/end timestamps snap to nearest Whisper phrase boundaries.
   - **Dual Categorization**:
     - **Shorts** (35s to 175s, < 3 minutes): Tagged with `#Shorts`.
     - **Mini-Long** (3 to 6 minutes max): Deep discussions categorized as regular YouTube videos.
   - Generates Roman Urdu Twitter hook question (< 90 chars), YouTube titles, descriptions, and hashtags.

4. **OpenCV Auto Face-Centering (`modules/face_engine.py`)**:
   - Multi-frame sampling (5 frames across duration) with median filtering to prevent single-frame anomalies.
   - Automatically calculates horizontal crop offset so the speaker is always centered in the 1:1 box.

5. **Dual-Language Subtitle Engine (`modules/subtitle_engine.py`)**:
   - **Top Line (Arabic)**: Quranic Ayat / Hadith in Golden/Amber (`#FBBF24`) with HarfBuzz/Raqm diacritics (Harakat) preservation.
   - **Bottom Line (English)**: Crisp Solid White (`#FFFFFF`) translation with 2-line word wrapping.
   - **2px Dark Outline Stroke**: 100% readable over bright/white clothing (e.g. white kurta and pagri).

6. **Template Compositor (`modules/video_engine.py`)**:
   - Renders onto the official template with dynamic bold typography and adaptive font sizing.
   - Explicit composite duration `-t` and dynamic duration-scaled timeout.

---

## 🛠️ API Endpoints (Protected by `X-API-Key`)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check and wake ping (open) |
| `POST` | `/api/extract-topics` | **Stage 1**: Extracts candidate clips with timestamps & metadata |
| `POST` | `/api/render-clip-async` | **Stage 2**: Dispatches asynchronous rendering job (returns `clip_id`) |
| `GET` | `/api/job-status/{clip_id}` | Polling endpoint for job completion and download URL |
| `GET` | `/api/download/{job_id}/{file}` | Streams final rendered MP4 |
| `DELETE` | `/api/jobs/{clip_id}` | Purges temporary job directory after YouTube upload |

---

## ⚡ n8n Workflows

1. **Stage 1 (`n8n_stage1_extract_topics.json`)**:
   - Monitors 4 official MTM YouTube channels via RSS with round-robin selection.
   - Calls `/api/extract-topics` and appends topics to Google Sheet `Clips_Queue`.
   - Runs on daily schedule at 22:00 (10:00 PM IST).

2. **Stage 2 (`n8n_stage2_render_and_publish.json`)**:
   - Wakes Render container, polls for render completion with Milan Voima async polling.
   - Uploads to YouTube with native scheduled publishing (`publishAt` in 5 spaced IST slots).
   - Updates Google Sheet row to `completed` and sends Telegram confirmation.
