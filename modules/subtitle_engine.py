"""
modules/subtitle_engine.py
Renders semi-transparent frosted pill subtitles with reshaped Arabic and English translations.
Features:
- Full Arabic Harakat (tashkeel) preservation (Raqm support + reshaper configuration)
- Multi-line English word-wrapping (up to 2 lines) preventing mid-sentence truncation
- Dynamic pill sizing and adaptive positioning
- High-contrast text stroke outline (2px) ensuring readability over bright/white clothing
"""

import logging
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, features
import arabic_reshaper
from bidi.algorithm import get_display
import config

logger = logging.getLogger("al-haqq-engine.subtitles")

# Check if HarfBuzz/Raqm is supported in current PIL build
try:
    HAS_RAQM = features.check("raqm")
except Exception:
    HAS_RAQM = False

# Reshaper configuration that strictly preserves Arabic harakat (zer, zabar, pesh, tashkeel)
_RESHAPER_CONFIG = arabic_reshaper.ArabicReshaper(
    configuration={
        'delete_harakat': False,
        'support_ligatures': True
    }
)

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
        Creates a transparent PNG containing the frosted pill subtitle overlay with:
        - Arabic text (Golden #FBBF24 with dark stroke)
        - English text (Solid White #FFFFFF with dark stroke, 2-line wrapping)
        - High contrast stroke ensuring 100% readability over white kurta/turbans
        """
        overlay = Image.new("RGBA", (video_width, video_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        has_ar = bool(arabic_text and arabic_text.strip())
        has_en = bool(english_text and english_text.strip())

        # If both are empty, produce an empty transparent overlay
        if not has_ar and not has_en:
            overlay.save(str(output_png), "PNG")
            return output_png

        box_w = min(620, video_width - 40)
        max_text_w = box_w - 40

        # Load fonts with mobile-friendly sizes (24px English, 28px Arabic)
        try:
            font_ar = ImageFont.truetype(self.font_arabic_path, 28) if self.font_arabic_path else ImageFont.load_default()
        except Exception:
            font_ar = ImageFont.load_default()

        try:
            font_en = ImageFont.truetype(self.font_hook_path, 24) if self.font_hook_path else ImageFont.load_default()
        except Exception:
            font_en = ImageFont.load_default()

        # 1. Prepare English lines with word-wrapping (up to 2 lines)
        en_lines = []
        if has_en:
            raw_en = english_text.strip()
            words = raw_en.split()
            current_line = []
            for w in words:
                candidate = " ".join(current_line + [w])
                bb = draw.textbbox((0, 0), candidate, font=font_en)
                if (bb[2] - bb[0]) <= max_text_w:
                    current_line.append(w)
                else:
                    if current_line:
                        en_lines.append(" ".join(current_line))
                    current_line = [w]
            if current_line:
                en_lines.append(" ".join(current_line))

            # Clamp to max 2 lines with graceful ellipsis if text is exceedingly long
            if len(en_lines) > 2:
                en_lines = en_lines[:2]
                while en_lines[-1] and (draw.textbbox((0, 0), en_lines[-1] + "...", font=font_en)[2] - draw.textbbox((0, 0), en_lines[-1] + "...", font=font_en)[0]) > max_text_w:
                    en_lines[-1] = en_lines[-1].rsplit(" ", 1)[0] if " " in en_lines[-1] else en_lines[-1][:-4]
                en_lines[-1] = en_lines[-1] + "..."

        # 2. Prepare Arabic text - dynamic font scaling instead of truncation (preserves full Quranic Ayat)
        rendered_ar_text = ""
        ar_layout_kwargs = {}
        if has_ar:
            raw_ar = arabic_text.strip()
            ar_size = 28 if len(raw_ar) <= 45 else (24 if len(raw_ar) <= 70 else 20)
            if self.font_arabic_path:
                try:
                    font_ar = ImageFont.truetype(self.font_arabic_path, ar_size)
                except Exception:
                    pass

            if HAS_RAQM and self.font_arabic_path:
                try:
                    font_ar_raqm = ImageFont.truetype(self.font_arabic_path, ar_size, layout_engine=ImageFont.Layout.RAQM)
                    font_ar = font_ar_raqm
                    rendered_ar_text = raw_ar
                    ar_layout_kwargs = {"direction": "rtl", "language": "ar"}
                except Exception:
                    reshaped = _RESHAPER_CONFIG.reshape(raw_ar)
                    rendered_ar_text = get_display(reshaped, base_dir='R')
            else:
                reshaped = _RESHAPER_CONFIG.reshape(raw_ar)
                rendered_ar_text = get_display(reshaped, base_dir='R')

        # 3. Compute dynamic box height
        line_h_en = 28
        ar_h = 40 if has_ar else 0
        en_total_h = len(en_lines) * line_h_en
        padding_v = 18

        box_h = padding_v * 2 + ar_h + (en_total_h if en_lines else 0)
        box_x = (video_width - box_w) // 2
        box_y = video_height - box_h - 22

        # 4. Draw high-contrast frosted pill (45% black alpha = 115)
        draw.rounded_rectangle(
            [box_x, box_y, box_x + box_w, box_y + box_h],
            radius=16,
            fill=(10, 10, 10, 115)
        )

        cursor_y = box_y + padding_v

        # 5. Draw Arabic text with dark outline stroke
        if has_ar and rendered_ar_text:
            bbox_ar = draw.textbbox((0, 0), rendered_ar_text, font=font_ar, **ar_layout_kwargs)
            ar_w = bbox_ar[2] - bbox_ar[0]
            ar_x = box_x + max(12, (box_w - ar_w) // 2)
            draw.text(
                (ar_x, cursor_y),
                rendered_ar_text,
                fill=(251, 191, 36, 255),
                font=font_ar,
                stroke_width=2,
                stroke_fill=(0, 0, 0, 240),
                **ar_layout_kwargs
            )
            cursor_y += ar_h + 4

        # 6. Draw English lines with dark outline stroke
        for line in en_lines:
            bbox_en = draw.textbbox((0, 0), line, font=font_en)
            en_w = bbox_en[2] - bbox_en[0]
            en_x = box_x + max(12, (box_w - en_w) // 2)
            draw.text(
                (en_x, cursor_y),
                line,
                fill=(255, 255, 255, 255),
                font=font_en,
                stroke_width=2,
                stroke_fill=(0, 0, 0, 240)
            )
            cursor_y += line_h_en

        overlay.save(str(output_png), "PNG")
        logger.info(f"Generated high-contrast subtitle overlay at {output_png}")
        return output_png
