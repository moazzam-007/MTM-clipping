# Al Haqq YouTube Shorts & Mini-Long Video Engine (`@al__haqqq`)

Fully automated video repurposing service that monitors long Islamic lectures (Mufti Tariq Masood), transcribes with Whisper, extracts complete engaging topics using Gemini, and renders them onto the **Al Haqq Twitter-style vertical template** (`720x1280`) with **Arabic & English subtitles**.

---

## 🚀 Key Pipeline Features

1. **Lightweight YouTube Streamer (`modules/youtube_engine.py`)**:
   - Streams audio and cuts 720p HD clips directly from YouTube without downloading full multi-gigabyte videos.
   - Bypasses bot checks using Node.js runtime and Android player client.

2. **Groq Whisper Large-v3 Speech-to-Text (`modules/transcription_engine.py`)**:
   - Ultra-fast transcription of Urdu speech with word/segment timestamps.
   - Dual Groq API key rotation with automatic failover.

3. **Gemini AI Topic Classifier (`modules/gemini_engine.py`)**:
   - **Zero "Adhuri Baat" Rule**: Identifies complete questions, rulings, and naseehat from start to finish.
   - **Dual Categorization**:
     - **Shorts** (45s to 175s, < 3 minutes): Optimized for YouTube Shorts shelf.
     - **Mini-Long** (3 to 6 minutes max): Deep discussions categorized as regular YouTube videos.
   - Generates Roman Urdu Twitter hook question (< 90 chars), YouTube titles, descriptions, and hashtags.

4. **OpenCV Auto Face-Centering (`modules/face_engine.py`)**:
   - Detects the speaker's face coordinates in the video frame using Haar Cascades.
   - Automatically calculates the horizontal crop offset so the speaker is always centered in the 1:1 box.

5. **Dual-Language Subtitle Engine (`modules/subtitle_engine.py`)**:
   - **Top Line (Arabic)**: Quranic Ayat / Hadith in Golden/Amber (`#FBBF24`) with proper bidirectional Arabic reshaping.
   - **Bottom Line (English)**: Crisp Solid White (`#FFFFFF`) translation.
   - **35% Frosted Black Scrim**: Placed inside the lower 20% of the video box, safely above the YouTube Shorts overlay and red seek bar.

6. **Template Compositor (`modules/video_engine.py`)**:
   - Renders onto the official `AL HAQQQ TEMP.jpg` template with dynamic bold typography.
   - 100% memory-safe streaming for Render.com free tier (512MB RAM limit).

---

## 🛠️ API Endpoints

- `GET /health` -> Healthcheck endpoint
- `POST /api/process-video` -> Starts async video processing job
  ```json
  {
    "url": "https://youtu.be/z_9E0w_2IwY",
    "max_clips": 5,
    "webhook_url": "https://your-n8n-instance.com/webhook/video-ready"
  }
  ```
  Returns:
  ```json
  {
    "job_id": "job_1a2b3c4d",
    "status": "queued",
    "status_url": "/api/status/job_1a2b3c4d"
  }
  ```
- `GET /api/status/{job_id}` -> Checks progress (0 to 100%) and returns rendered clips list.
- `GET /api/download/{job_id}/{clip_filename}` -> Downloads final rendered MP4.

---

## 📦 Local Setup & Testing

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure .env with your credentials
# (Copy from .env.example)

# 3. Start local development server
python main.py
```

---

## ☁️ Deploy to Render.com (100% Free Tier)

1. Push this repository to GitHub.
2. In Render.com Dashboard:
   - Click **New** -> **Blueprint**.
   - Select your repository.
   - Render detects `render.yaml` and deploys the Docker container.
3. Add Environment Variables:
   - `GEMINI_API_KEY`
   - `GROQ_API_KEY`
   - `GROQ_API_KEY_FALLBACK`
   - `API_SECRET_KEY`

---

## ⚡ n8n Workflow Automation

Import `n8n_workflow_shorts.json` into your n8n instance:
- Monitors the YouTube channel RSS feed for new lecture uploads.
- Calls Render `/api/process-video`.
- Downloads completed clips and uploads directly to your YouTube channel using the n8n **YouTube Node**.
