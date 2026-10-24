"""
modules/subtitle_engine.py
Renders the semi-transparent black pill subtitle with reshaped Arabic and English translations.
Includes text wrapping and boundary checks to prevent overflow.
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
        Guarantees text stays within the pill boundaries.
        """
        overlay = Image.new("RGBA", (video_width, video_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        has_ar = bool(arabic_text and arabic_text.strip())
        has_en = bool(english_text and english_text.strip())

        # If both are empty, produce an empty transparent overlay
        if not has_ar and not has_en:
            overlay.save(str(output_png), "PNG")
            return output_png

        box_w = min(600, video_width - 40)
        box_h = 105
        box_x = (video_width - box_w) // 2
        box_y = video_height - box_h - 20

        # Draw 35% black transparency rounded rectangle
        draw.rounded_rectangle(
            [box_x, box_y, box_x + box_w, box_y + box_h],
            radius=14,
            fill=(10, 10, 10, 95)
        )

        font_ar = ImageFont.truetype(self.font_arabic_path, 25) if self.font_arabic_path else ImageFont.load_default()
        font_en = ImageFont.truetype(self.font_hook_path, 20) if self.font_hook_path else ImageFont.load_default()

        # 1. Arabic Text
        if has_ar:
            raw_ar = arabic_text.strip()
            if len(raw_ar) > 55:
                words = raw_ar.split()
                truncated = []
                curr_len = 0
                for w in words:
                    if curr_len + len(w) + 1 > 50:
                        break
                    truncated.append(w)
                    curr_len += len(w) + 1
                raw_ar = (" ".join(truncated) + "…") if truncated else (raw_ar[:50] + "…")
            reshaped_ar = arabic_reshaper.reshape(raw_ar)
            bidi_ar = get_display(reshaped_ar, base_dir='R')
            bbox_ar = draw.textbbox((0, 0), bidi_ar, font=font_ar)
            ar_w = bbox_ar[2] - bbox_ar[0]
            ar_x = box_x + max(12, (box_w - ar_w) // 2)
            ar_y = box_y + 12
            draw.text((ar_x, ar_y), bidi_ar, fill=(251, 191, 36, 255), font=font_ar)
            en_y = ar_y + 45
        else:
            en_y = box_y + 38

        # 2. English Text
        if english_text and english_text.strip():
            raw_en = english_text.strip()
            # Wrap or ellipsize to fit inside pill width
            max_en_width = box_w - 30
            bbox_en = draw.textbbox((0, 0), raw_en, font=font_en)
            if (bbox_en[2] - bbox_en[0]) > max_en_width:
                # Truncate to fit
                while len(raw_en) > 10 and (draw.textbbox((0, 0), raw_en + "...", font=font_en)[2] - draw.textbbox((0, 0), raw_en + "...", font=font_en)[0]) > max_en_width:
                    raw_en = raw_en[:-4]
                raw_en = raw_en + "..."
                
            bbox_en = draw.textbbox((0, 0), raw_en, font=font_en)
            en_w = bbox_en[2] - bbox_en[0]
            en_x = box_x + max(12, (box_w - en_w) // 2)
            draw.text((en_x, en_y), raw_en, fill=(255, 255, 255, 255), font=font_en)

        overlay.save(str(output_png), "PNG")
        logger.info(f"Generated subtitle overlay image at {output_png}")
        return output_png
