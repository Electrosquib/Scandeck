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

def signal_bars(draw, x, y, level):
    for i in range(5):
        h = 8 + i * 7
        x0 = x + i * 10
        y0 = y + 40 - h
        fill = (80, 220, 120) if i < level else (50, 60, 70)
        draw.rounded_rectangle((x0, y0, x0 + 7, y + 40), radius = 2, fill = fill)

def draw_spectrum(draw, x, y, w, h, t):
    rr(draw, (x, y, x + w, y + h), 12, fill = (12, 18, 28), outline = (36, 50, 68), width = 2)
    for i in range(1, 5):
        yy = y + int(h * i / 5)
        draw.line((x + 8, yy, x + w - 8, yy), fill = (26, 38, 52), width = 1)
    for i in range(1, 7):
        xx = x + int(w * i / 7)
        draw.line((xx, y + 8, xx, y + h - 8), fill = (26, 38, 52), width = 1)

    pts = []
    for i in range(w - 16):
        xx = x + 8 + i
        a = math.sin((i / 18.0) + t * 2.0) * 16
        b = math.sin((i / 7.0) + t * 1.1) * 6
        c = 24 * math.exp(-((i - (w * 0.58)) ** 2) / 1800)
        yy = y + h - 22 - int(a + b + c)
        pts.append((xx, yy))

    for i in range(len(pts) - 1):
        draw.line((pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]), fill = (60, 220, 180), width = 2)

    cx = x + int(w * 0.58)
    draw.line((cx, y + 10, cx, y + h - 10), fill = (255, 200, 60), width = 2)

def make_ui(data, t):
    img = Image.new("RGB", (480, 320), (8, 12, 18))
    draw = ImageDraw.Draw(img)

    lock = Image.open("/home/scandeck-one/Scandeck/UI/img/lock.png").convert("RGBA")
    lock = lock.resize((30, 30))

    font_xs = safe_font(14)
    font_sm = safe_font(19)
    font_md = safe_font(24, bold = True)
    font_lg = safe_font(36, bold = True)

    # === TOP BAR ===
    draw.rectangle((0, 0, 480, 50), fill = (10, 16, 24))
    draw.line((0, 49, 480, 49), fill = (32, 46, 62), width = 2)

    draw.text((45, 15), data["system"], font = font_sm, fill = (120, 150, 180))

    # right status
    draw.text((330, 8), f"{data['freq']}", font = font_sm, fill = (255, 255, 255))
    draw.text((330, 27), f"NAC: {data['nac']}", font = font_xs, fill = (160, 200, 220))

    # === LEFT MAIN (talkgroup + alias) ===
    rr(draw, (10, 60, 300, 190), 14, fill = (14, 20, 30), outline = (36, 50, 68), width = 2)
    draw.text((20, 70), "Talkgroup", font = font_xs, fill = (120, 150, 180))
    draw.text((20, 95), data["alias"], font = font_md, fill = (160, 235, 255))

    # rr(draw, (10, 160, 300, 230), 14, fill = (14, 20, 30), outline = (36, 50, 68), width = 2)
    # draw.text((20, 170), "Alias", font = font_xs, fill = (120, 150, 180))
    draw.text((240, 70), data["talkgroup"], font = font_xs, fill = (160, 235, 255))

    # === RIGHT PANEL (signal + system info) ===

    draw.text((135, 150), f"{data['rssi']} dBm", font = font_sm, fill = (190, 210, 230))
    draw.text((20, 135), f"Site: {data['site']}", font = font_xs, fill = (120, 150, 180))
    draw.text((20, 160), f"WACN: {data['wacn']}", font = font_xs, fill = (120, 150, 180))

    rr(draw, (310, 60, 470, 190), 14, fill = (14, 20, 30), outline = (36, 50, 68), width = 2)

    signal_bars(draw, 235, 130, data["signal"])

    # === SPECTRUM (wide) ===
    draw_spectrum(draw, 10, 200, 460, 60, t)

    # === BOTTOM BUTTONS ===
    rr(draw, (10, 270, 110, 310), 8, fill = (80, 220, 120))
    rr(draw, (120, 270, 240, 310), 8, fill = (10, 16, 24), outline = (36, 50, 68), width = 2)
    rr(draw, (250, 270, 350, 310), 8, fill = (10, 16, 24), outline = (36, 50, 68), width = 2)
    rr(draw, (360, 270, 460, 310), 8, fill = (10, 16, 24), outline = (36, 50, 68), width = 2)

    draw.text((23, 277), "SCAN", font = font_md, fill = (36, 50, 68))
    draw.text((150, 277), "SKIP", font = font_md, fill = (255, 255, 255))
    draw.text((275, 277), "REC", font = font_md, fill = (255, 255, 255))
    draw.text((372, 277), "MENU", font = font_md, fill = (255, 255, 255))

    if data['encrypted'] == 1:
        img.paste(lock, (8, 8), lock)

    return img
