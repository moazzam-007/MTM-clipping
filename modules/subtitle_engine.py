"""
modules/subtitle_engine.py
Renders the semi-transparent black pill subtitle with reshaped Arabic and English translations.
"""

import logging
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
import config

logger = logging.getLogger("al-haqq-engine.subtitles")

class SubtitleEngine:
    def __init__(self):
        self.font_hook_path = config.FONT_HOOK
        self.font_arabic_path = config.FONT_ARABIC

    def create_caption_overlay(
        self,
        video_width: int,
        video_height: int,
        arabic_text: str,
        english_text: str,
        output_png: Path
    ) -> Path:
        """
        Creates a transparent PNG containing the 35% black frosted pill with
        Arabic (Golden #FBBF24) and English (Solid White #FFFFFF) text.
        """
        overlay = Image.new("RGBA", (video_width, video_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Box dimensions & placement: lower 20% of video
        box_w = min(600, video_width - 40)
        box_h = 100
        box_x = (video_width - box_w) // 2
        box_y = video_height - box_h - 20

        # Draw 35% black transparency rounded rectangle (alpha = 95/255)
        draw.rounded_rectangle(
            [box_x, box_y, box_x + box_w, box_y + box_h],
            radius=14,
            fill=(10, 10, 10, 95)
        )

        # Fonts
        font_ar = ImageFont.truetype(self.font_arabic_path, 25) if self.font_arabic_path else ImageFont.load_default()
        font_en = ImageFont.truetype(self.font_hook_path, 20) if self.font_hook_path else ImageFont.load_default()

        # 1. Arabic Text (Reshaped & BiDi)
        if arabic_text and arabic_text.strip():
            reshaped_ar = arabic_reshaper.reshape(arabic_text.strip())
            bidi_ar = get_display(reshaped_ar)
            bbox_ar = draw.textbbox((0, 0), bidi_ar, font=font_ar)
            ar_w = bbox_ar[2] - bbox_ar[0]
            ar_x = box_x + max(10, (box_w - ar_w) // 2)
            ar_y = box_y + 12
            draw.text((ar_x, ar_y), bidi_ar, fill=(251, 191, 36, 255), font=font_ar)
            en_y = ar_y + 44
        else:
            en_y = box_y + 35

        # 2. English Text (Crisp Solid White)
        if english_text and english_text.strip():
            # Truncate or wrap if too long
            en_clean = english_text.strip()
            bbox_en = draw.textbbox((0, 0), en_clean, font=font_en)
            en_w = bbox_en[2] - bbox_en[0]
            en_x = box_x + max(10, (box_w - en_w) // 2)
            draw.text((en_x, en_y), en_clean, fill=(255, 255, 255, 255), font=font_en)

        overlay.save(str(output_png), "PNG")
        logger.info(f"Generated subtitle overlay image at {output_png}")
        return output_png
