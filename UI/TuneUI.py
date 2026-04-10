from PIL import Image, ImageDraw, ImageFont
import time
import math

def safe_font(size, bold=False):
    choices = [
        "/home/scandeck-one/Scandeck/fonts/DejaVuSans-Bold.ttf"
        if bold
        else "/home/scandeck-one/Scandeck/fonts/DejaVuSans.ttf",
    ]
    for path in choices:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()

def rr(draw, xy, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)

def draw_spectrum(draw, x, y, width, height, t):
    # Simple spectrum placeholder
    for i in range(width):
        h = int(height * (0.5 + 0.5 * math.sin(t * 0.1 + i * 0.1)))
        draw.line((x + i, y + height, x + i, y + height - h), fill=(0, 255, 0), width=1)

def make_ui(freq=851.4125, modulation="CQPSK", bandwidth="12.5k", t=0):
    img = Image.new("RGB", (480, 320), (8, 12, 18))
    draw = ImageDraw.Draw(img)

    fonts = {
        "xs": safe_font(13),
        "sm": safe_font(17),
        "md": safe_font(21, bold=True),
        "lg": safe_font(28, bold=True),
    }

    # Top info
    draw.text((10, 10), f"Freq: {freq} MHz", font=fonts["md"], fill=(255, 255, 255))
    draw.text((10, 40), f"Mod: {modulation}", font=fonts["sm"], fill=(160, 200, 220))
    draw.text((10, 60), f"BW: {bandwidth}", font=fonts["sm"], fill=(160, 200, 220))

    # Spectrum on bottom
    draw_spectrum(draw, 10, 200, 460, 60, t)

    # Buttons below spectrum
    button_y = 270
    button_height = 40
    button_width = 100
    buttons = ["Tune -", "Tune +", "Mod/BW", "Menu"]
    for i, label in enumerate(buttons):
        x0 = 10 + i * (button_width + 10)
        x1 = x0 + button_width
        y0 = button_y
        y1 = y0 + button_height
        rr(draw, (x0, y0, x1, y1), 10, fill=(10, 16, 24), outline=(36, 50, 68), width=2)
        draw.text((x0 + 10, y0 + 10), label, font=fonts["sm"], fill=(255, 255, 255))

    return img