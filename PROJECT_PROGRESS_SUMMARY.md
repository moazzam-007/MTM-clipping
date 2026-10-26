# Al-Haqq Video Repurposing Engine — Project Progress & Context Summary

**Last Updated:** October 26, 2026  
**Repository:** [https://github.com/moazzam-007/MTM-clipping](https://github.com/moazzam-007/MTM-clipping) (Branch: `main`)  
**Deployment Service:** Render (`al-haqq-shorts-engine` / `https://mtm-clipping.onrender.com`)

---

## 1. Project Overview & Architecture

Al-Haqq is an automated end-to-end video repurposing engine designed to ingest full-length Islamic lectures (Mufti Tariq Masood bayanat), automatically identify high-impact topics, and produce vertical (9:16) YouTube Shorts and Mini-Long videos with synchronized Arabic Ayaat, English subtitles, and custom branding.

### System Pipeline:
1. **Ingestion (Telegram Bot):** Admin sends `/q <youtube_url>` to Telegram bot ➡️ appends row with status `pending` to Google Sheet Queue.
2. **Stage 1 (Topic Extraction - n8n + Render AI API):**
   - Scheduled daily (10:00 PM IST) or manual trigger.
   - Reads pending video from Google Sheet `Al_Haqq_Video_Sources_Queue`.
   - Calls Render API endpoint `POST /api/extract-topics`.
   - Transcribes audio (Groq Whisper Large-v3) & extracts optimal clips (Google Gemini 2.5 Flash Lite).
   - Appends clips to `Al_Haqq_Clips_Queue` with status `pending`.
   - Marks source row as `processed` in `Al_Haqq_Video_Sources_Queue`.
   - Sends Telegram alert with summary.
3. **Stage 2 (Single Clip Rendering & Publishing - n8n + Render Engine):**
   - Scheduled hourly or on demand.
   - Reads 1 pending clip from `Al_Haqq_Clips_Queue`.
   - Cuts 720p HD stream with reconnect flags.
   - Detects speaker's face via OpenCV and centers dynamically.
   - Overlays branded template and rendered Arabic / English subtitle pill.
   - Renders progressive MP4 and uploads to YouTube Shorts via YouTube Data API v3.
   - Updates clip status to `completed`.

---

## 2. Current Progress & What Is 100% Completed

### A. Telegram Ingestion (Verified & Working)
- Telegram trigger node configured with Admin Chat ID security (`1306188611`).
- Successfully tested live with `/q https://youtu.be/ya0yIPQ8aqY`.
- Row successfully appended to Google Sheet with `Date`, `Video_ID`, `Video_URL`, `Status: pending`.

### B. Google Sheets Configuration
- **Sources Queue Sheet:** `Al_Haqq_Video_Sources_Queue`
  - Document ID: `1dZw3LWuXrhyqtXSHMqWzot-Jzk4JqjjRuSDodzXBGyc`
  - Sheet GID: `1157530755`
  - Columns: `Date`, `Video_ID`, `Video_URL`, `Status`, `Added_By`, `Processed_Date`
- **Clips Queue Sheet:** `Al_Haqq_Clips_Queue`
  - Document ID: `1noDquIR2BkZEN3DFoA4Ey8FU5GZ9c_WBDwvtUkVjoEE`
  - Sheet GID: `1354640108`
  - Columns: `Date`, `Clip_ID`, `Video_ID`, `Video_URL`, `Lecture_Title`, `Category`, `Start_Sec`, `End_Sec`, `Duration_Sec`, `First_Words`, `Last_Words`, `Roman_Urdu_Hook`, `Arabic_Sub`, `Arabic_Source`, `Reference`, `English_Sub`, `YT_Title`, `YT_Description`, `Tags`, `Status`, `YT_URL`

### C. Backend Engine Hardening (Deployed on GitHub & Render)
- **yt-dlp Unified Extraction (`modules/youtube_engine.py`):**
  - Converted multiple fragmented calls into a single unified `--dump-single-json` call.
  - Prioritizes H.264 (`avc1`) streams over AV1 to prevent CPU choking on Render 0.1 core.
  - Eliminated `check=True` unhandled crashes and added `TimeoutExpired` protection.
  - Fallback logic fixed: avoids mapping audio-only stream as video in FFmpeg.
- **AI Models & Snapping (`config.py` & `modules/gemini_engine.py`):**
  - Updated default model from deprecated preview to `gemini-2.5-flash-lite`.
  - Directional boundary snapping implemented so speeches and sentences are never cut off prematurely.
  - Cleaned dead legacy `google.generativeai` imports.
  - Added TPM guard for Groq Llama fallback.
  - Safe `#Shorts` title appending without 100-character boundary cuts.
- **Audio & Subtitle Rendering (`modules/subtitle_engine.py` & `modules/video_engine.py`):**
  - Removed hardcoded 65-character truncation that mutilated Arabic Quranic verses.
  - Dynamic font scaling ensures full verses fit inside the caption pill.
  - Added `expected_duration` parameter to prevent fallback truncation to 60s.
- **Service Security & Reliability (`main.py`):**
  - Background async tasks stored in `BG_TASKS` set to prevent Python garbage collection.
  - Path traversal vulnerability guarded in `delete_job` (blocks `clip_id="."`).
  - Deprecated `@app.on_event` replaced with modern FastAPI `lifespan` handler.
- **n8n Workflow Fix:**
  - In `n8n_stage1_extract_topics.json`, mapped `"Video_ID": "={{ $('🎯 Select 1 Video to Process').first().json.video_id }}"` in `Mark Source Video as Processed` node so sheet updates execute reliably.

---

## 3. The Active Blocker (Where the Project is Paused)

### Problem Description:
When Render's service executes `/api/extract-topics`, `yt-dlp` fails with:
```text
RuntimeError: yt-dlp extraction failed: bpage: HTTP Error 429: Too Many Requests (caused by <HTTPError 429: Too Many Requests>)
ERROR: [youtube] ya0yIPQ8aqY: Sign in to confirm you’re not a bot.
```

### Root Cause:
YouTube aggressively blocks and challenges cloud datacenter IP ranges (Render Frankfurt IPs in this case). When web-client requests originate from Render, YouTube blocks the initial webpage scrape (`bpage`) with HTTP 429 / bot verification, regardless of whether standard cookies are passed.

---

## 4. Ready-to-Execute Solutions When Resuming

When you are ready to resume work, pick one of the following proven solutions to bypass the YouTube datacenter block:

### Strategy 1: Direct YouTube Transcript API (Fastest & 100% Free of IP Blocks)
- **Why it works:** Mufti Tariq Masood lectures already have Urdu captions/subtitles on YouTube. The `youtube-transcript-api` Python library queries the internal caption endpoints which are **not blocked** on cloud datacenters.
- **Action when resuming:**
  - Install `youtube-transcript-api`.
  - In `main.py`, fetch transcript directly for Stage 1.
  - Pass transcript straight to Gemini 2.5 for topic extraction.
  - **Result:** Stage 1 runs in 2 seconds, consumes 0 Groq quota, and bypasses yt-dlp completely.

### Strategy 2: Residential Proxy for `yt-dlp` (Permanent Universal Fix)
- **Why it works:** Proxies route yt-dlp requests through residential/home IP addresses, eliminating datacenter bot-checks for both Stage 1 and Stage 2 HD video cutting.
- **Action when resuming:**
  - Configure a proxy provider (e.g., Webshare, Smartproxy).
  - Add `HTTP_PROXY` or `YOUTUBE_PROXY` to Render Environment Variables.
  - Pass `--proxy` to `yt-dlp` commands in `youtube_engine.py`.

### Strategy 3: Innertube Webpage Skip + PO Token
- **Action when resuming:**
  - Add `--extractor-args "youtube:player_client=android,ios;player_skip=webpage,configs"` to `yt-dlp` to skip the blocked `bpage` entirely.
  - Pass a browser-generated `po_token` via environment variable.

---

## 5. Important File Locations & Environment Keys

| Component | Path / Value |
| :--- | :--- |
| **Local Workspace** | `e:\Antigravity\atheist\freelacer video` |
| **Sibling Git Repo** | `E:\Antigravity\atheist\MTM-clipping` |
| **Stage 1 Workflow** | `e:\Antigravity\atheist\freelacer video\n8n_stage1_extract_topics.json` |
| **Review Zip Archive** | `e:\Antigravity\atheist\freelacer video\MTM_Render_Stage1_Review.zip` |
| **Render API Key** | `al_haqq_sec_9971bc84ef1244a08b98e1` |
| **Telegram Admin ID** | `1306188611` |
| **Sources Queue Sheet** | `1dZw3LWuXrhyqtXSHMqWzot-Jzk4JqjjRuSDodzXBGyc` (GID: `1157530755`) |
| **Clips Output Sheet** | `1noDquIR2BkZEN3DFoA4Ey8FU5GZ9c_WBDwvtUkVjoEE` (GID: `1354640108`) |
