from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "/home/scandeck-one/Scandeck/UI/fonts"
FONT_CACHE = {}

BG = (8, 12, 18)
PANEL = (14, 20, 30)
PANEL_ALT = (10, 16, 24)
OUTLINE = (36, 50, 68)
TEXT = (235, 240, 248)
MUTED = (120, 150, 180)
ACCENT = (80, 220, 120)
ACCENT_TEXT = (10, 16, 24)
HILITE = (160, 235, 255)

TUNE_MENU_BTN = (10, 8, 118, 42)
TUNE_FREQ_PANEL = (12, 58, 468, 108)
TUNE_MOD_BUTTONS = [
    ("FM", (12, 118, 120, 151)),
    ("AM", (128, 118, 236, 151)),
    ("LSB", (244, 118, 352, 151)),
    ("USB", (360, 118, 468, 151)),
]
TUNE_BW_UP_BTN = (12, 160, 92, 236)
TUNE_BW_DOWN_BTN = (12, 244, 92, 315)
TUNE_KEYPAD_BUTTONS = [
    ("1", (104, 160, 184, 195)),
    ("2", (192, 160, 272, 195)),
    ("3", (280, 160, 360, 195)),
    ("4", (104, 201, 184, 236)),
    ("5", (192, 201, 272, 236)),
    ("6", (280, 201, 360, 236)),
    ("7", (104, 241, 184, 275)),
    ("8", (192, 241, 272, 275)),
    ("9", (280, 241, 360, 275)),
    ("·", (104, 281, 184, 315)),
    ("0", (192, 281, 272, 315)),
    ("DEL", (280, 281, 360, 315)),
]
# TUNE_KEYPAD_BUTTONS = TUNE_KEYPAD_BUTTONS

TUNE_FILTER_PANEL = (372, 170, 468, 310)

BW_MIN = 2500
BW_MAX = 25000


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


def rr(draw, xy, radius, fill = None, outline = None, width = 1):
    draw.rounded_rectangle(xy, radius = radius, fill = fill, outline = outline, width = width)


def format_frequency(freq_value):
    try:
        return f"{float(freq_value):.4f}".rstrip("0").rstrip(".")
    except Exception:
        return str(freq_value)


def format_bandwidth_label(bandwidth_hz):
    value = float(bandwidth_hz)
    if value >= 1000:
        text = f"{value / 1000:.1f}".rstrip("0").rstrip(".")
        return f"{text} kHz"
    return f"{int(value)} Hz"


def draw_centered_text(draw, rect, text, font, fill):
    bbox = draw.textbbox((0, 0), text, font = font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = rect[0] + (rect[2] - rect[0] - text_w) // 2
    y = rect[1] + (rect[3] - rect[1] - text_h) // 2 - 3
    draw.text((x, y), text, font = font, fill = fill)


def draw_button(draw, rect, label, font, selected = False):
    fill = ACCENT if selected else PANEL_ALT
    outline = ACCENT if selected else OUTLINE
    text_fill = ACCENT_TEXT if selected else TEXT
    rr(draw, rect, 10, fill = fill, outline = outline, width = 2)
    draw_centered_text(draw, rect, label, font, text_fill)


def draw_filter_graphic(draw, rect, bandwidth_hz, font_sm, font_xs):
    rr(draw, rect, 12, fill = PANEL, outline = OUTLINE, width = 2)
    draw.text((rect[0] + 10, rect[1] + 8), "FILTER", font = font_xs, fill = MUTED)
    draw.text((rect[0] + 10, rect[1] + 24), format_bandwidth_label(bandwidth_hz), font = font_sm, fill = HILITE)

    graph_left = rect[0] + 10
    graph_top = rect[1] + 54
    graph_right = rect[2] - 10
    graph_bottom = rect[3] - 14
    center_x = (graph_left + graph_right) // 2
    center_y = (graph_top + graph_bottom) // 2

    rr(draw, (graph_left, graph_top, graph_right, graph_bottom), 10, fill = PANEL_ALT, outline = OUTLINE, width = 1)
    draw.line((graph_left + 2, graph_bottom, graph_right - 2, graph_bottom), fill = PANEL_ALT, width = 3)
    draw.line((graph_left + 8, center_y, graph_right - 8, center_y), fill = OUTLINE, width = 1)
    draw.line((center_x, graph_top + 8, center_x, graph_bottom - 8), fill = OUTLINE, width = 1)

    span = max(0.14, min(0.92, (float(bandwidth_hz) - BW_MIN) / (BW_MAX - BW_MIN)))
    half_width = int((graph_right - graph_left - 24) * span / 2)
    fill_rect = (
        center_x - half_width,
        center_y - 18,
        center_x + half_width,
        center_y + 18,
    )
    rr(draw, fill_rect, 8, fill = (28, 90, 62), outline = ACCENT, width = 2)


def make_ui(freq = 146.52, modulation = "FM", bandwidth = 12500, t = 0, freq_text = None):
    img = Image.new("RGB", (480, 320), BG)
    draw = ImageDraw.Draw(img)

    font_xs = safe_font(14)
    font_sm = safe_font(17)
    font_md = safe_font(20, bold = True)
    font_lg = safe_font(32, bold = True)

    draw.rectangle((0, 0, 480, 50), fill = PANEL_ALT)
    draw.line((0, 49, 480, 49), fill = OUTLINE, width = 2)
    draw_button(draw, TUNE_MENU_BTN, "MENU", font_sm, selected = False)
    draw.text((208, 10), "TUNE", font = safe_font(26, bold = True), fill = TEXT)

    rr(draw, TUNE_FREQ_PANEL, 14, fill = PANEL, outline = OUTLINE, width = 2)
    # draw.text((24, 60), "FREQUENCY", font = font_xs, fill = MUTED)
    freq_display = format_frequency(freq) if freq_text is None else str(freq_text)
    draw.text((25, 65), freq_display, font = font_lg, fill = TEXT)
    draw.text((390, 72), "MHz", font = font_md, fill = HILITE)

    for label, rect in TUNE_MOD_BUTTONS:
        draw_button(draw, rect, label, font_sm, selected = (label.upper() == str(modulation).upper()))

    draw_button(draw, TUNE_BW_UP_BTN, "BW +", font_md)
    draw_button(draw, TUNE_BW_DOWN_BTN, "BW -", font_md)

    for label, rect in TUNE_KEYPAD_BUTTONS:
        draw_button(draw, rect, label, font_md, selected = False)

    draw_filter_graphic(draw, TUNE_FILTER_PANEL, bandwidth, font_sm, font_xs)

    return img
