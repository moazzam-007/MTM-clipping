import os
from PIL import Image, ImageDraw, ImageFont

def create_preview(hook_text="Agar namaz ke liye late ho rahe he to kya sirf Farz wuzu kar sakte he.?"):
    template_path = "AL HAQQQ TEMP.jpg"
    img = Image.open(template_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    
    # Fonts
    font_path = "C:/Windows/Fonts/segoeuib.ttf"
    if not os.path.exists(font_path):
        font_path = "C:/Windows/Fonts/arialbd.ttf"
    
    font_size = 32
    font = ImageFont.truetype(font_path, font_size)
    
    # Text wrapping
    max_width = 620
    x_start = 50
    y_start = 280
    
    words = hook_text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
    if current_line:
        lines.append(" ".join(current_line))
        
    # Draw lines
    line_height = 42
    current_y = y_start
    for line in lines:
        draw.text((x_start, current_y), line, fill=(0, 0, 0), font=font)
        current_y += line_height
        
    # Video container area guide (simulating where the video goes)
    # Video area: from y=current_y + 20 to y=current_y + 20 + 640 (square 1:1) or 16:9
    video_top = max(current_y + 25, 420)
    video_width = 640
    video_height = 640 # Square 1:1 format like screenshot 4!
    video_left = (720 - video_width) // 2
    
    # Draw a placeholder box for video preview
    draw.rectangle(
        [video_left, video_top, video_left + video_width, video_top + video_height],
        outline=(200, 200, 200),
        fill=(30, 30, 30),
        width=2
    )
    draw.text(
        (video_left + 220, video_top + 300),
        "[ VIDEO BOX 1:1 ]",
        fill=(255, 255, 255),
        font=font
    )
    
    img.save("test_layout_preview.jpg", quality=95)
    print(f"Saved layout preview to test_layout_preview.jpg! Video top: {video_top}")

if __name__ == "__main__":
    create_preview()
