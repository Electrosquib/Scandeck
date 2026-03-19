import time
import math
import spidev
import RPi.GPIO as GPIO
from PIL import Image, ImageDraw, ImageFont

WIDTH = 480
HEIGHT = 320

DC = 6
RST = 5
BL = 12
SPI_BUS = 0
SPI_DEV = 0
SPI_HZ = int(62.5e6)

class ST7796:
    def __init__(self, spi_bus = SPI_BUS, spi_dev = SPI_DEV, dc = DC, rst = RST, bl = BL):
        self.width = WIDTH
        self.height = HEIGHT
        self.dc = dc
        self.rst = rst
        self.bl = bl

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self.dc, GPIO.OUT)
        GPIO.setup(self.rst, GPIO.OUT)
        GPIO.setup(self.bl, GPIO.OUT)

        self.spi = spidev.SpiDev()
        self.spi.open(spi_bus, spi_dev)
        self.spi.max_speed_hz = SPI_HZ
        self.spi.mode = 0

        self.reset()
        self.init_display()
        GPIO.output(self.bl, 1)

    def reset(self):
        GPIO.output(self.rst, 1)
        time.sleep(0.05)
        GPIO.output(self.rst, 0)
        time.sleep(0.05)
        GPIO.output(self.rst, 1)
        time.sleep(0.15)

    def cmd(self, c):
        GPIO.output(self.dc, 0)
        self.spi.writebytes([c])

    def data(self, d):
        GPIO.output(self.dc, 1)
        if isinstance(d, int):
            self.spi.writebytes([d])
        else:
            chunk = 4096
            for i in range(0, len(d), chunk):
                self.spi.writebytes(d[i:i + chunk])

    def init_display(self):
        self.cmd(0x01)
        time.sleep(0.15)

        self.cmd(0x11)
        time.sleep(0.12)

        self.cmd(0x36)
        self.data(0xE8)

        self.cmd(0x3A)
        self.data(0x55)

        self.cmd(0xF0)
        self.data(0xC3)
        self.cmd(0xF0)
        self.data(0x96)

        self.cmd(0xB4)
        self.data(0x01)

        self.cmd(0xB7)
        self.data(0xC6)

        self.cmd(0xC0)
        self.data([0x80, 0x45])

        self.cmd(0xC1)
        self.data(0x13)

        self.cmd(0xC2)
        self.data(0xA7)

        self.cmd(0xC5)
        self.data(0x1A)

        self.cmd(0xE8)
        self.data([0x40, 0x8A, 0x00, 0x00, 0x29, 0x19, 0xA5, 0x33])

        self.cmd(0xE0)
        self.data([0xF0, 0x06, 0x0B, 0x08, 0x07, 0x05, 0x2E, 0x33, 0x47, 0x3A, 0x17, 0x16, 0x2E, 0x31])

        self.cmd(0xE1)
        self.data([0xF0, 0x09, 0x0D, 0x09, 0x08, 0x23, 0x2E, 0x33, 0x46, 0x38, 0x13, 0x13, 0x2C, 0x32])

        self.cmd(0xF0)
        self.data(0x3C)
        self.cmd(0xF0)
        self.data(0x69)

        self.cmd(0x21)
        self.cmd(0x29)
        time.sleep(0.05)

    def set_window(self, x0, y0, x1, y1):
        self.cmd(0x2A)
        self.data([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])
        self.cmd(0x2B)
        self.data([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])
        self.cmd(0x2C)

    def show(self, image):
        if image.size != (self.width, self.height):
            image = image.resize((self.width, self.height))
        rgb = image.convert("RGB")
        raw = rgb.load()

        buf = bytearray(self.width * self.height * 2)
        p = 0
        for y in range(self.height):
            for x in range(self.width):
                r, g, b = raw[x, y]
                rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                buf[p] = rgb565 >> 8
                buf[p + 1] = rgb565 & 0xFF
                p += 2

        self.set_window(0, 0, self.width - 1, self.height - 1)
        self.data(buf)

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

    font_xs = safe_font(14)
    font_sm = safe_font(19)
    font_md = safe_font(24, bold = True)
    font_lg = safe_font(36, bold = True)

    # === TOP BAR ===
    draw.rectangle((0, 0, 480, 50), fill = (10, 16, 24))
    draw.line((0, 49, 480, 49), fill = (32, 46, 62), width = 2)

    # draw.text((10, 10), "P25 SCANNER", font = font_md, fill = (235, 240, 248))
    draw.text((10, 15), data["system"], font = font_sm, fill = (120, 150, 180))

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
    draw.text((145, 277), "HOLD", font = font_md, fill = (255, 255, 255))
    draw.text((260, 277), "MENU", font = font_md, fill = (255, 255, 255))
    draw.text((380, 277), "REC", font = font_md, fill = (255, 255, 255))

    return img


def demo_data():
    return {
        "system": "Honolulu Public Safety",
        "talkgroup": "12048",
        "alias": "DISPATCH EAST",
        "freq": "852.7125 MHz",
        "nac": "0x293",
        "site": "001-014",
        "wacn": "BEE00",
        "rssi": "-71",
        "signal": 4
    }

def main():
    lcd = ST7796()
    t = 0.0
    while True:
        data = demo_data()
        img = make_ui(data, t)
        lcd.show(img)
        t += 0.08
        time.sleep(0.01)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        GPIO.cleanup()
