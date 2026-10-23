import os
import subprocess
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

def render_sample_with_captions():
    base_img = Image.open("AL HAQQQ TEMP.jpg").convert("RGBA")
    hook_text = "Dil jab galat cheezein sune to kya hota hai?"
    draw = ImageDraw.Draw(base_img)
    
    font_path_bold = "C:/Windows/Fonts/segoeuib.ttf"
    if not os.path.exists(font_path_bold):
        font_path_bold = "C:/Windows/Fonts/arialbd.ttf"
    font_hook = ImageFont.truetype(font_path_bold, 32)
    
    draw.text((50, 280), hook_text, fill=(0, 0, 0, 255), font=font_hook)
    
    video_left = 40
    video_top = 360
    video_size = 640
    
    frame_path = "mtm_clip_frame.jpg"
    mtm_frame = Image.open(frame_path).convert("RGBA")
    w, h = mtm_frame.size
    min_dim = min(w, h)
    left = (w - min_dim) // 2
    top = (h - min_dim) // 2
    mtm_square = mtm_frame.crop((left, top, left + min_dim, top + min_dim))
    mtm_square = mtm_square.resize((video_size, video_size), Image.Resampling.LANCZOS)
    
    caption_overlay = Image.new("RGBA", (video_size, video_size), (0, 0, 0, 0))
    cap_draw = ImageDraw.Draw(caption_overlay)
    
    box_w = 600
    box_h = 100
    box_x = (video_size - box_w) // 2
    box_y = video_size - box_h - 20
    
    # 35% black transparency rounded pill
    cap_draw.rounded_rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h],
        radius=14,
        fill=(10, 10, 10, 100)
    )
    
    font_arabic = ImageFont.truetype("C:/Windows/Fonts/tahoma.ttf", 26)
    font_english = ImageFont.truetype(font_path_bold, 21)
    
    # Arabic with proper reshaping and BiDi direction
    raw_arabic = "إِنَّ فِي الْجَسَدِ مُضْغَةً إِذَا صَلَحَتْ"
    reshaped_arabic = arabic_reshaper.reshape(raw_arabic)
    bidi_arabic = get_display(reshaped_arabic)
    
    bbox_ar = cap_draw.textbbox((0, 0), bidi_arabic, font=font_arabic)
    ar_w = bbox_ar[2] - bbox_ar[0]
    ar_x = box_x + (box_w - ar_w) // 2
    ar_y = box_y + 12
    cap_draw.text((ar_x, ar_y), bidi_arabic, fill=(251, 191, 36, 255), font=font_arabic)
    
    english_text = "Indeed, in the body there is a piece of flesh..."
    bbox_en = cap_draw.textbbox((0, 0), english_text, font=font_english)
    en_w = bbox_en[2] - bbox_en[0]
    en_x = box_x + (box_w - en_w) // 2
    en_y = ar_y + 44
    cap_draw.text((en_x, en_y), english_text, fill=(255, 255, 255, 255), font=font_english)
    
    mtm_with_captions = Image.alpha_composite(mtm_square, caption_overlay)
    base_img.paste(mtm_with_captions, (video_left, video_top))
    
    final_preview = base_img.convert("RGB")
    final_preview.save("caption_design_sample.jpg", quality=95)
    print("Updated caption_design_sample.jpg with properly shaped Arabic!")

if __name__ == "__main__":
    render_sample_with_captions()
