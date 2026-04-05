import time
import math
import spidev
import RPi.GPIO as GPIO
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "/home/scandeck-one/Scandeck/UI/fonts"
FONT_CACHE = {}
ICON_CACHE = {}
MENU_CACHE = None

def safe_font(size, bold = False):
    key = (size, bold)
    if key in FONT_CACHE:
        return FONT_CACHE[key]

    path = f"{FONT_DIR}/DejaVuSans-Bold.ttf" if bold else f"{FONT_DIR}/DejaVuSans.ttf"
    try:
        font = ImageFont.truetype(path, size)
    except Exception:
        font = ImageFont.load_default()
    FONT_CACHE[key] = font
    return font

def load_icon(name, size):
    key = (name, size)
    if key not in ICON_CACHE:
        ICON_CACHE[key] = Image.open(f"/home/scandeck-one/Scandeck/UI/img/{name}").convert("RGBA").resize(size)
    return ICON_CACHE[key]

def rr(draw, xy, radius, fill = None, outline = None, width = 1):
    draw.rounded_rectangle(xy, radius = radius, fill = fill, outline = outline, width = width)


def make_ui(selected_index, t = 0):
    global MENU_CACHE

    if MENU_CACHE is not None:
        return MENU_CACHE.copy()

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

        rr(draw, (x0, y0, x1, y1), 12, fill = (10, 16, 24), outline = (36, 50, 68), width = 2)
        text_color = "#FFFFFF"

        # center text
        tw, th = draw.textbbox((0, 0), label, font = font_md)[2:]
        tx = x0 + (tile_w - tw) // 2
        ty = y0 + (tile_h - th) // 2 + 32

        draw.text((tx, ty), label, font = font_md, fill = text_color)

    lock = load_icon("settings.png", (50, 50))
    img.paste(lock, (363, 207), lock)

    lock = load_icon("list.png", (50, 50))
    img.paste(lock, (68, 80), lock)

    lock = load_icon("spectrum.png", (50, 50))
    img.paste(lock, (215, 80), lock)

    lock = load_icon("radar.png", (50, 50))
    img.paste(lock, (363, 80), lock)

    lock = load_icon("wifi.png", (50, 50))
    img.paste(lock, (68, 207), lock)

    lock = load_icon("record.png", (50, 50))
    img.paste(lock, (215, 207), lock)

    MENU_CACHE = img
    return img.copy()
