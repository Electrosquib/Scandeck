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
    # rr(draw, (10, 8, 123, 42), 8, fill = (80, 220, 120))
    # draw.text((32, 13), "SCAN", font = font_md, fill = (10, 16, 24))

    draw.text((190, 10), "MENU", font = font_lg, fill = (235, 240, 248))

    # === GRID SETUP ===
    tiles = [
        "SCAN",
        "LIST",
        "TUNE",
        "ADS-B",
    ]

    cols = 2
    rows = 2
    tile_w = 210
    tile_h = 110
    gap_x = 14
    gap_y = 14
    start_x = 23
    start_y = 70

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
        ty = y0 + (tile_h - th) // 2 + 30

        draw.text((tx, ty), label, font = font_md, fill = text_color)

    icon_positions = [
        ("scan.png", (103, 84)),
        ("list.png", (327, 84)),
        ("spectrum.png", (103, 208)),
        ("radar.png", (327, 208)),
    ]

    for icon_name, position in icon_positions:
        icon = load_icon(icon_name, (50, 50))
        img.paste(icon, position, icon)

    MENU_CACHE = img
    return img.copy()
