import time
import math
import spidev
import RPi.GPIO as GPIO
from PIL import Image, ImageDraw, ImageFont

def safe_font(size, bold = False):
    choices = [
        "/home/scandeck-one/Scandeck/fonts/DejaVuSans-Bold.ttf" if bold else "/home/scandeck-one/Scandeck/fonts/DejaVuSans.ttf",
    ]
    for path in choices:
        try:
            return ImageFont.truetype(path, size)
        except:
            pass
    return ImageFont.load_default()

def rr(draw, xy, radius, fill = None, outline = None, width = 1):
    draw.rounded_rectangle(xy, radius = radius, fill = fill, outline = outline, width = width)


def make_ui(selected_index, t = 0):
    img = Image.new("RGB", (480, 320), (8, 12, 18))
    draw = ImageDraw.Draw(img)

    font_sm = safe_font(18)
    font_md = safe_font(22, bold = True)
    font_lg = safe_font(26, bold = True)

    # === TOP BAR ===
    draw.rectangle((0, 0, 480, 50), fill = (10, 16, 24))
    draw.line((0, 49, 480, 49), fill = (32, 46, 62), width = 2)

    # back to scan button (top-left)
    rr(draw, (10, 8, 123, 42), 8, fill = (80, 220, 120))
    draw.text((17, 13), "◀ SCAN", font = font_md, fill = (10, 16, 24))

    draw.text((190, 10), "MENU", font = font_lg, fill = (235, 240, 248))

    # === GRID SETUP ===
    tiles = [
        "LISTS",
        "TUNE",
        "ADS-B",
        "HOTSPOT",
        "RECORD",
        "SETTINGS"
    ]

    cols = 3
    rows = 2
    tile_w = 140
    tile_h = 120
    gap_x = 10
    gap_y = 10
    start_x = 18
    start_y = 60

    for i, label in enumerate(tiles):
        col = i % cols
        row = i // cols

        x0 = start_x + col * (tile_w + gap_x)
        y0 = start_y + row * (tile_h + gap_y)
        x1 = x0 + tile_w
        y1 = y0 + tile_h

        if i == selected_index:
            rr(draw, (x0, y0, x1, y1), 12, fill = (60, 180, 255))
            text_color = (10, 16, 24)
        else:
            rr(draw, (x0, y0, x1, y1), 12, fill = (14, 20, 30), outline = (200, 220, 240), width = 2)
            text_color = "#50dc78" #(200, 220, 240)

        # center text
        tw, th = draw.textbbox((0, 0), label, font = font_md)[2:]
        tx = x0 + (tile_w - tw) // 2
        ty = y0 + (tile_h - th) // 2 + 32

        draw.text((tx, ty), label, font = font_md, fill = text_color)

    lock = Image.open("/home/scandeck-one/Scandeck/UI/img/settings.png").convert("RGBA")
    lock = lock.resize((50, 50))
    img.paste(lock, (363, 207), lock)

    lock = Image.open("/home/scandeck-one/Scandeck/UI/img/list.png").convert("RGBA")
    lock = lock.resize((50, 50))
    img.paste(lock, (68, 80), lock)

    lock = Image.open("/home/scandeck-one/Scandeck/UI/img/spectrum.png").convert("RGBA")
    lock = lock.resize((50, 50))
    img.paste(lock, (215, 80), lock)

    lock = Image.open("/home/scandeck-one/Scandeck/UI/img/radar.png").convert("RGBA")
    lock = lock.resize((50, 50))
    img.paste(lock, (363, 80), lock)

    lock = Image.open("/home/scandeck-one/Scandeck/UI/img/wifi.png").convert("RGBA")
    lock = lock.resize((50, 50))
    img.paste(lock, (68, 207), lock)

    lock = Image.open("/home/scandeck-one/Scandeck/UI/img/record.png").convert("RGBA")
    lock = lock.resize((50, 50))
    img.paste(lock, (215, 207), lock)

    return img