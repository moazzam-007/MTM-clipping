import os
import sys
import json
import time
import subprocess
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from groq import Groq
import google.generativeai as genai

# Load environment variables
load_dotenv(".env")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_FALLBACK = os.getenv("GROQ_API_KEY_FALLBACK")

TEMPLATE_IMG = "AL HAQQQ TEMP.jpg"
YOUTUBE_URL = "https://youtu.be/z_9E0w_2IwY"
AUDIO_TEST_FILE = "lecture_sample_audio.mp3"
TRANSCRIPT_CACHE_FILE = "transcript_cache.json"
FINAL_OUTPUT_SHORT = "final_mtm_short.mp4"

def get_stream_url(video_url: str) -> str:
    print(f"[1/6] Fetching video stream URL via yt-dlp...")
    cmd = [
        "yt-dlp",
        "--js-runtimes", "node",
        "--extractor-args", "youtube:player_client=android",
        "-f", "18",
        "-g",
        video_url
    ]
    res = subprocess.check_output(cmd, text=True).strip().splitlines()
    stream_url = res[-1]
    print(f"      Stream URL fetched successfully!")
    return stream_url

def extract_sample_audio(stream_url: str, duration_sec: int = 900) -> str:
    if os.path.exists(AUDIO_TEST_FILE) and os.path.getsize(AUDIO_TEST_FILE) > 100000:
        print(f"[2/6] Using existing cached audio file ({AUDIO_TEST_FILE})...")
        return AUDIO_TEST_FILE
        
    print(f"[2/6] Streaming {duration_sec//60} mins of audio at 32k mono...")
    ff_cmd = [
        "ffmpeg", "-y",
        "-ss", "120", # Skip intro greetings/salaam
        "-t", str(duration_sec),
        "-i", stream_url,
        "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k",
        AUDIO_TEST_FILE
    ]
    subprocess.check_call(ff_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"      Audio saved to {AUDIO_TEST_FILE} ({os.path.getsize(AUDIO_TEST_FILE)/1024:.1f} KB)")
    return AUDIO_TEST_FILE

def transcribe_with_groq(audio_path: str):
    if os.path.exists(TRANSCRIPT_CACHE_FILE):
        print(f"[3/6] Loading cached transcript from {TRANSCRIPT_CACHE_FILE}...")
        with open(TRANSCRIPT_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
            
    print(f"[3/6] Transcribing audio with Groq Whisper Large-v3...")
    client = Groq(api_key=GROQ_API_KEY)
    try:
        with open(audio_path, "rb") as f:
            res = client.audio.transcriptions.create(
                file=("audio.mp3", f),
                model="whisper-large-v3",
                response_format="verbose_json"
            )
    except Exception as e:
        print(f"      Primary Groq key error: {e}. Trying fallback key...")
        client = Groq(api_key=GROQ_FALLBACK)
        with open(audio_path, "rb") as f:
            res = client.audio.transcriptions.create(
                file=("audio.mp3", f),
                model="whisper-large-v3",
                response_format="verbose_json"
            )
            
    data = {
        "text": res.text,
        "segments": res.segments
    }
    with open(TRANSCRIPT_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    print(f"      Transcription complete & cached! Total text length: {len(res.text)} chars.")
    return data

def analyze_best_clip_with_llm(transcript_obj):
    print(f"[4/6] Analyzing lecture with AI to extract viral short clip...")
    
    # Build text with segment timestamps
    segments_summary = []
    for s in transcript_obj.get("segments", []):
        start = s.get("start", 0) + 120
        end = s.get("end", 0) + 120
        text = s.get("text", "").strip()
        segments_summary.append(f"[{start:.1f}s - {end:.1f}s]: {text}")
        
    transcript_text = "\n".join(segments_summary[:100]) # First 100 segments
    
    prompt = f"""
Aap ek expert YouTube Shorts & Instagram Reels editor hain jo Mufti Tariq Masood ke bayanat se viral shorts cut karte hain.

Yeh bayan ke segments timestamps ke sath hain:
\"\"\"
{transcript_text}
\"\"\"

Aapko isme se sabse ZABARDAST, self-contained aur engaging topic/clip choose karni hai (Duration must be between 30 to 60 seconds).
Ek aisa clip chuno jisme koi clear question, naseehat ya ahem masla bayan ho raha ho.

Mera template Twitter/X style card hai (@al__haqqq).
Mujhe:
1. "start_time": Clip ka start time in seconds (float ya integer)
2. "end_time": Clip ka end time in seconds (float ya integer)
3. "roman_urdu_hook": Ek short, intriguing Roman Urdu Twitter question/hook under 90 characters (jaise: 'Agar namaz ke liye late ho rahe he to kya sirf Farz wuzu kar sakte he.?')
4. "yt_title": Catchy YouTube Shorts Title with #Shorts #MuftiTariqMasood
5. "description": 2-3 lines description

Return STRICTLY valid JSON ONLY, no markdown, no explanation:
{{
  "start_time": 150.0,
  "end_time": 195.0,
  "roman_urdu_hook": "...",
  "yt_title": "...",
  "description": "..."
}}
"""
    raw_text = None
    # 1. Try Gemini Models with Flash Lite
    genai.configure(api_key=GEMINI_API_KEY)
    for model_name in ["gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-1.5-flash"]:
        try:
            print(f"      Calling Gemini ({model_name})...")
            model = genai.GenerativeModel(model_name)
            res = model.generate_content(prompt)
            raw_text = res.text.strip()
            print(f"      Success with {model_name}!")
            break
        except Exception as e:
            print(f"      {model_name} failed: {e}. Trying next...")
            time.sleep(2)
            
    # 2. Fallback to Groq Qwen/Llama if Gemini hits rate limits
    if not raw_text:
        print("      Trying Groq LLM as fallback...")
        groq_client = Groq(api_key=GROQ_API_KEY)
        chat_completion = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="qwen/qwen3.8-27b",
        )
        raw_text = chat_completion.choices[0].message.content.strip()
        print("      Success with Groq LLM fallback!")
        
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
    if raw_text.startswith("```"):
        raw_text = raw_text[3:]
    if raw_text.endswith("```"):
        raw_text = raw_text[:-3]
    raw_text = raw_text.strip()
    
    data = json.loads(raw_text)
    print(f"      Selected Clip: [{data['start_time']}s to {data['end_time']}s] (Duration: {data['end_time'] - data['start_time']:.1f}s)")
    print(f"      Hook Text: \"{data['roman_urdu_hook']}\"")
    print(f"      YT Title: \"{data['yt_title']}\"")
    return data

def cut_video_clip(stream_url: str, start_time: float, end_time: float, output_path: str = "raw_clip.mp4"):
    duration = end_time - start_time
    print(f"[5/6] Cutting video clip ({duration:.1f}s) from stream...")
    ff_cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_time),
        "-i", stream_url,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        output_path
    ]
    subprocess.check_call(ff_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"      Raw clip saved to {output_path}")
    return output_path

def render_short_video(raw_clip_path: str, hook_text: str, output_path: str):
    print(f"[6/6] Rendering final vertical Short on '{TEMPLATE_IMG}'...")
    
    # 1. Overlay hook text
    base_img = Image.open(TEMPLATE_IMG).convert("RGB")
    draw = ImageDraw.Draw(base_img)
    
    font_path = "C:/Windows/Fonts/segoeuib.ttf"
    if not os.path.exists(font_path):
        font_path = "C:/Windows/Fonts/arialbd.ttf"
    
    font = ImageFont.truetype(font_path, 32)
    max_width = 620
    x_start = 50
    y_start = 280
    
    words = hook_text.split()
    lines = []
    current_line = []
    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
    if current_line:
        lines.append(" ".join(current_line))
        
    line_height = 42
    current_y = y_start
    for line in lines:
        draw.text((x_start, current_y), line, fill=(0, 0, 0), font=font)
        current_y += line_height
        
    overlay_bg_path = "rendered_template_bg.png"
    base_img.save(overlay_bg_path)
    
    # Video position: 1:1 square centered horizontally
    video_top = max(current_y + 25, 420)
    video_left = 40
    video_size = 640
    
    # 2. Composite with FFmpeg
    ff_render_cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", overlay_bg_path,
        "-i", raw_clip_path,
        "-filter_complex",
        f"[1:v]scale=w={video_size}:h={video_size}:force_original_aspect_ratio=increase,crop={video_size}:{video_size}[vclip];"
        f"[0:v][vclip]overlay={video_left}:{video_top}:shortest=1[outv]",
        "-map", "[outv]",
        "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path
    ]
    subprocess.check_call(ff_render_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"      SUCCESS! Final Short created at: {output_path}")

def run_pipeline():
    print("==================================================")
    print("STARTING AUTOMATED CLIPPING & SHORT CREATION TEST")
    print("==================================================")
    
    stream_url = get_stream_url(YOUTUBE_URL)
    audio_path = extract_sample_audio(stream_url, duration_sec=900)
    transcript = transcribe_with_groq(audio_path)
    clip_info = analyze_best_clip_with_llm(transcript)
    raw_clip = cut_video_clip(stream_url, clip_info["start_time"], clip_info["end_time"])
    render_short_video(raw_clip, clip_info["roman_urdu_hook"], FINAL_OUTPUT_SHORT)
    
    print("\n==================================================")
    print("PIPELINE TEST FINISHED SUCCESSFULLY!")
    print(f"Output File: {FINAL_OUTPUT_SHORT}")
    print(f"File Size: {os.path.getsize(FINAL_OUTPUT_SHORT)/(1024*1024):.2f} MB")
    print(f"Title: {clip_info['yt_title']}")
    print(f"Hook: {clip_info['roman_urdu_hook']}")
    print("==================================================")

if __name__ == "__main__":
    run_pipeline()
