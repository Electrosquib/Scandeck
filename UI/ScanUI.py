import time
import math
from collections import deque
import spidev
import RPi.GPIO as GPIO
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "/home/scandeck-one/Scandeck/UI/fonts"
FONT_CACHE = {}
ICON_CACHE = {}
BASE_IMAGE = None
CPU_HISTORY = deque()
CPU_PREV_TOTAL = None
CPU_PREV_IDLE = None

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

def truncate_text(text, max_chars):
    if text is None:
        return ""

    text = str(text)
    if len(text) <= max_chars:
        return text

    return text[:max_chars - 1] + "..."

def signal_bars(draw, x, y, level):
    for i in range(5):
        h = 8 + i * 7
        x0 = x + i * 10
        y0 = y + 40 - h
        fill = (80, 220, 120) if i < level else (50, 60, 70)
        draw.rounded_rectangle((x0, y0, x0 + 7, y + 40), radius = 2, fill = fill)

def read_total_cpu_usage():
    global CPU_PREV_TOTAL, CPU_PREV_IDLE

    total = 0
    idle = 0
    found_core = False

    try:
        with open("/proc/stat", "r") as stat_file:
            for line in stat_file:
                if not line.startswith("cpu"):
                    break

                parts = line.split()
                if not parts or parts[0] == "cpu":
                    continue

                values = [int(value) for value in parts[1:]]
                if len(values) < 4:
                    continue

                found_core = True
                total += sum(values)
                idle += values[3] + (values[4] if len(values) > 4 else 0)
    except Exception:
        return None

    if not found_core:
        return None

    if CPU_PREV_TOTAL is None or CPU_PREV_IDLE is None:
        CPU_PREV_TOTAL = total
        CPU_PREV_IDLE = idle
        return None

    delta_total = total - CPU_PREV_TOTAL
    delta_idle = idle - CPU_PREV_IDLE
    CPU_PREV_TOTAL = total
    CPU_PREV_IDLE = idle

    if delta_total <= 0:
        return None

    usage = (delta_total - delta_idle) / delta_total * 100.0
    return max(0.0, min(100.0, usage))

def get_cpu_history(length):
    usage = read_total_cpu_usage()

    while len(CPU_HISTORY) < length:
        CPU_HISTORY.append(0.0 if usage is None else usage)

    if usage is not None:
        CPU_HISTORY.append(usage)

    while len(CPU_HISTORY) > length:
        CPU_HISTORY.popleft()

    return list(CPU_HISTORY)

def draw_spectrum(draw, x, y, w, h, t):
    rr(draw, (x, y, x + w, y + h), 12, fill = (12, 18, 28), outline = (36, 50, 68), width = 2)
    for i in range(1, 5):
        yy = y + int(h * i / 5)
        draw.line((x + 8, yy, x + w - 8, yy), fill = (26, 38, 52), width = 1)
    for i in range(1, 7):
        xx = x + int(w * i / 7)
        draw.line((xx, y + 8, xx, y + h - 8), fill = (26, 38, 52), width = 1)

    pts = []
    history = get_cpu_history(w - 16)
    for i, usage in enumerate(history):
        xx = x + 8 + i
        usable_height = h - 20
        yy = y + h - 10 - int((usage / 100.0) * usable_height)
        pts.append((xx, yy))

    for i in range(len(pts) - 1):
        draw.line((pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]), fill = (60, 220, 180), width = 2)

    if history:
        font_xs = safe_font(14)
        draw.text((x + 8, y + 8), "CPU Usage", font = font_xs, fill = (120, 150, 180))
        draw.text((x + w - 40, y + 8), f"{int(round(history[-1]))}%", font = font_xs, fill = (120, 150, 180))

def draw_activity_history(draw, x, y, w, h, history):
    font_xs = safe_font(14)
    font_sm = safe_font(16, bold = True)
    draw.text((x + 12, y + 12), "Recent Activity", font = font_xs, fill = (120, 150, 180))
    if not history:
        draw.text((x + 12, y + 40), "No previous traffic", font = font_xs, fill = (90, 110, 130))
        return
    row_height = 30
    max_rows = max(1, min(len(history), (h - 30) // row_height))
    visible_history = history[:max_rows]
    for index, entry in enumerate(visible_history):
        row_top = y + 40 + (index * row_height)
        if index > 0:
            draw.line((x + 10, row_top - 4, x + w - 10, row_top - 4), fill = (26, 38, 52), width = 1)
        alias = truncate_text(entry.get("alias", ""), 17)
        if not alias:
            alias = truncate_text(entry.get("talkgroup", ""), 8)
        draw.text((x + 12, row_top + 2), alias, font = font_sm, fill = (160, 235, 255))
        # draw.text((x + 12, row_top + 14), alias, font = font_xs, fill = (190, 210, 230))

def build_base_image():
    img = Image.new("RGB", (480, 320), (8, 12, 18))
    draw = ImageDraw.Draw(img)
    font_xs = safe_font(14)
    font_md = safe_font(24, bold = True)
    draw.rectangle((0, 0, 480, 50), fill = (10, 16, 24))
    draw.line((0, 49, 480, 49), fill = (32, 46, 62), width = 2)
    rr(draw, (10, 60, 300, 190), 14, fill = (14, 20, 30), outline = (36, 50, 68), width = 2)
    draw.text((20, 70), "Talkgroup", font = font_xs, fill = (120, 150, 180))
    rr(draw, (310, 60, 470, 260), 14, fill = (14, 20, 30), outline = (36, 50, 68), width = 2)
    rr(draw, (10, 270, 110, 310), 8, fill = (80, 220, 120))
    rr(draw, (120, 270, 240, 310), 8, fill = (10, 16, 24), outline = (36, 50, 68), width = 2)
    rr(draw, (250, 270, 350, 310), 8, fill = (10, 16, 24), outline = (36, 50, 68), width = 2)
    rr(draw, (360, 270, 460, 310), 8, fill = (10, 16, 24), outline = (36, 50, 68), width = 2)
    draw.text((23, 277), "SCAN", font = font_md, fill = (36, 50, 68))
    draw.text((150, 277), "SKIP", font = font_md, fill = (255, 255, 255))
    draw.text((275, 277), "REC", font = font_md, fill = (255, 255, 255))
    draw.text((372, 277), "MENU", font = font_md, fill = (255, 255, 255))

    return img

def get_base_image():
    global BASE_IMAGE
    if BASE_IMAGE is None:
        BASE_IMAGE = build_base_image()
    return BASE_IMAGE

def make_ui(data, t):
    img = get_base_image().copy()
    draw = ImageDraw.Draw(img)

    lock = load_icon("lock.png", (30, 30))

    font_xs = safe_font(14)
    font_sm = safe_font(19)
    font_md = safe_font(24, bold = True)

    draw.text((45, 12), data["system"].upper(), font = font_md, fill = (255, 255, 255))

    # right status
    if data['freq'] == "-":
        freq_text = "-"
    else:
        freq_text = f"{round(int(data['freq'])/1e6, 4)} MHz"
    draw.text((330, 8), freq_text, font = font_sm, fill = (255, 255, 255))
    draw.text((330, 27), f"NAC: {data['nac'] if data['nac'] != 0 else ''}", font = font_xs, fill = (160, 200, 220))
    draw.text((20, 95), data["alias"] if data["alias"] != "-" else '', font = font_md, fill = (160, 235, 255))
    draw.text((240, 70), data["talkgroup"] if data["talkgroup"] != "-" else "", font = font_xs, fill = (160, 235, 255))
    draw.text((20, 135), f"Site: {data['site_alias'] if data['site_alias'] else ''} ({data['site'] if data['site'] else ''})", font = font_xs, fill = (120, 150, 180))
    # draw.text((20, 148), truncate_text(data.get("site_alias", ""), 28), font = font_xs, fill = (190, 210, 230))
    # draw.text((150, 160), f"{data['rssi']} dBm", font = font_xs, fill = (190, 210, 230))
    draw.text((20, 170), f"WACN: {data['wacn'] if data['wacn'] !=-1 else ''}", font = font_xs, fill = (120, 150, 180))

    signal_bars(draw, 235, 130, data["signal"])
    draw_spectrum(draw, 10, 200, 290, 60, t)
    draw_activity_history(draw, 310, 60, 160, 200, data.get("activity_history", []))

    if data['encrypted'] == 1:
        img.paste(lock, (8, 8), lock)

    return img
