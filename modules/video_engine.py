"""
modules/video_engine.py
Composites the dynamic Twitter card template, face-centered video clip, and subtitles into a final 9:16 MP4.
Includes memory limits and guaranteed cleanup of intermediate files.
"""

import os
import logging
import subprocess
from pathlib import Path
from typing import Tuple
from PIL import Image, ImageDraw, ImageFont
import cv2
import config
from modules.face_engine import FaceEngine
from modules.subtitle_engine import SubtitleEngine

logger = logging.getLogger("al-haqq-engine.video")

class VideoEngine:
    def __init__(self):
        self.template_path = config.TEMPLATE_PATH
        self.face_engine = FaceEngine()
        self.subtitle_engine = SubtitleEngine()
        self.font_hook_path = config.FONT_HOOK

    def prepare_template_with_hook(self, hook_text: str, output_path: Path) -> Tuple[Path, int]:
        """
        Loads AL HAQQQ TEMP.jpg, wraps and prints the Roman Urdu hook question,
        and returns the path to the background and the calculated bottom Y position.
        """
        with Image.open(self.template_path) as img:
            base_img = img.convert("RGB")
        draw = ImageDraw.Draw(base_img)

        font_size = 32
        font = ImageFont.truetype(self.font_hook_path, font_size) if self.font_hook_path else ImageFont.load_default()

        max_width = 620
        x_start = 50
        y_start = 280

        # Word wrap
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

        # Clamp max lines to 3 so it never pushes the video off canvas
        lines = lines[:3]

        line_height = 42
        current_y = y_start
        for line in lines:
            draw.text((x_start, current_y), line, fill=(0, 0, 0), font=font)
            current_y += line_height

        base_img.save(str(output_path), quality=95)
        logger.info(f"Generated template background with hook text at {output_path}")
        return output_path, current_y

    def render_final_video(
        self,
        raw_clip_path: Path,
        hook_text: str,
        arabic_text: str,
        english_text: str,
        output_mp4_path: Path
    ) -> Path:
        """
        Full composition pipeline with guaranteed cleanup and memory-safe FFmpeg encoding.
        """
        logger.info(f"Starting final video render for: {raw_clip_path.name}")
        temp_dir = output_mp4_path.parent
        bg_img_path = temp_dir / f"bg_{output_mp4_path.stem}.jpg"
        sub_overlay_path = temp_dir / f"sub_{output_mp4_path.stem}.png"

        try:
            # 1. Prepare Background with Hook Text
            _, last_text_y = self.prepare_template_with_hook(hook_text, bg_img_path)

            # 2. Get Video Box Placement (clamped to prevent canvas overflow)
            video_box_w = config.VIDEO_BOX_WIDTH
            video_box_h = config.VIDEO_BOX_HEIGHT
            video_box_left = config.VIDEO_BOX_LEFT
            video_box_top = min(max(last_text_y + 25, config.VIDEO_BOX_TOP), 450)

            # 3. Create Subtitle Overlay
            self.subtitle_engine.create_caption_overlay(
                video_width=video_box_w,
                video_height=video_box_h,
                arabic_text=arabic_text,
                english_text=english_text,
                output_png=sub_overlay_path
            )

            # 4. Detect Face & Calculate Crop Offset
            cap = cv2.VideoCapture(str(raw_clip_path))
            src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1280)
            src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 720)
            cap.release()

            square_dim = min(src_w, src_h)
            crop_x = self.face_engine.calculate_crop_x(raw_clip_path)
            if crop_x < 0:
                crop_x = (src_w - square_dim) // 2
                crop_x = crop_x - (crop_x % 2)

            crop_y = max(0, (src_h - square_dim) // 2)
            crop_y = crop_y - (crop_y % 2)

            logger.info(f"Video geometry: {src_w}x{src_h} -> crop {square_dim}x{square_dim} at x={crop_x}, y={crop_y}")

            # 5. FFmpeg Stream Composition with strict memory and thread caps
            ff_cmd = [
                "ffmpeg", "-y",
                "-nostdin", "-loglevel", "error",
                "-loop", "1", "-i", str(bg_img_path),
                "-i", str(raw_clip_path),
                "-loop", "1", "-i", str(sub_overlay_path),
                "-filter_complex",
                (
                    f"[1:v]crop=w={square_dim}:h={square_dim}:x={crop_x}:y={crop_y},"
                    f"scale={video_box_w}:{video_box_h}[v_scaled];"
                    f"[v_scaled][2:v]overlay=0:0:shortest=1[v_with_sub];"
                    f"[0:v][v_with_sub]overlay={video_box_left}:{video_box_top}:shortest=1[outv]"
                ),
                "-map", "[outv]",
                "-map", "1:a?",
                "-threads", "1",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-bufsize", "2M",
                "-c:a", "aac", "-b:a", "128k",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                str(output_mp4_path)
            ]

            res = subprocess.run(ff_cmd, capture_output=True, text=True, timeout=240)
            if res.returncode != 0:
                logger.error(f"FFmpeg composite failed: {res.stderr[-400:]}")
                raise RuntimeError(f"FFmpeg composite failed: {res.stderr[-200:]}")

            logger.info(f"Final video rendered successfully: {output_mp4_path} ({output_mp4_path.stat().st_size / (1024*1024):.2f} MB)")
            return output_mp4_path

        finally:
            # Guaranteed cleanup of intermediate temporary image files
            if bg_img_path.exists():
                bg_img_path.unlink()
            if sub_overlay_path.exists():
                sub_overlay_path.unlink()
