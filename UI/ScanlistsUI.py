from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "/home/scandeck-one/Scandeck/UI/fonts"
FONT_CACHE = {}


def safe_font(size, bold=False):
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


def rr(draw, xy, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def _fit_text(draw, text, font, max_width):
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text

    trimmed = text
    while len(trimmed) > 1:
        trimmed = trimmed[:-1]
        candidate = trimmed + "..."
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            return candidate
    return "..."


def _normalize_scanlists(scanlists):
    if not scanlists:
        return []
    out = []
    for item in scanlists:
        if isinstance(item, dict):
            out.append(str(item.get("name", "Unnamed")))
        else:
            out.append(str(item))
    return out


def _normalize_sites(sites):
    if not sites:
        return []
    out = []
    for item in sites:
        if isinstance(item, dict):
            label = item.get("description") or item.get("name") or item.get("label") or "Unnamed Site"
            out.append(str(label))
        elif isinstance(item, str):
            out.append(item)
        else:
            out.append(str(item))
    return out


def _draw_list_panel(draw, title, items, selected_index, box, fonts, accent):
    x0, y0, x1, y1 = box
    rr(draw, box, 16, fill=(14, 20, 30), outline=(36, 50, 68), width=2)
    draw.text((x0 + 12, y0 + 8), title, font=fonts["xs"], fill=(120, 150, 180))
    row_h = 34
    top = y0 + 28
    bottom = y1 - 30
    visible_rows = max(1, (bottom - top) // row_h)
    start = 0
    if items and selected_index >= visible_rows:
        start = selected_index - visible_rows + 1
    visible = items[start:start + visible_rows]

    if not visible:
        draw.text((x0 + 14, top + 18), "No entries loaded", font=fonts["sm"], fill=(110, 130, 150))
        return

    for offset, label in enumerate(visible):
        item_index = start + offset
        row_y = top + offset * row_h
        active = item_index == selected_index
        bg = accent if active else (18, 28, 40)
        fg = (10, 16, 24) if active else (235, 240, 248)
        outline = None if active else (32, 46, 62)
        rr(draw, (x0 + 8, row_y, x1 - 8, row_y + 28), 8, fill=bg, outline=outline, width=1)
        draw.text((x0 + 16, row_y + 5), _fit_text(draw, label, fonts["sm"], x1 - x0 - 40), font=fonts["sm"], fill=fg)


def _draw_arrow_button(draw, box, label, fonts, fill, text_fill):
    rr(draw, box, 10, fill=fill, outline=(36, 50, 68), width=2 if fill != (80, 220, 120) else 1)
    tx0, ty0, tx1, ty1 = draw.textbbox((0, 0), label, font=fonts["lg"])
    ty0 -= 10
    text_w = tx1 - tx0
    text_h = ty1 - ty0
    x0, y0, x1, y1 = box
    draw.text((x0 + (x1 - x0 - text_w) // 2, y0 + (y1 - y0 - text_h) // 2 - 2), label, font=fonts["lg"], fill=text_fill)


def make_ui(scanlists=None, selected_scanlist=0, sites=None, selected_site=0, t=0):
    scanlists = _normalize_scanlists(scanlists)
    sites = _normalize_sites(sites)

    img = Image.new("RGB", (480, 320), (8, 12, 18))
    draw = ImageDraw.Draw(img)

    fonts = {
        "xs": safe_font(13),
        "sm": safe_font(17),
        "md": safe_font(21, bold=True),
        "lg": safe_font(28, bold=True),
    }

    draw.rectangle((0, 0, 480, 50), fill=(10, 16, 24))
    draw.line((0, 49, 480, 49), fill=(32, 46, 62), width=2)

    back_btn = (10, 8, 108, 42)
    save_btn = (366, 8, 460, 42)
    left_panel = (10, 60, 230, 310)
    right_panel = (250, 60, 470, 310)

    rr(draw, back_btn, 10, fill=(10, 16, 24), outline=(36, 50, 68), width=2)
    draw.text((25, 12), "BACK", font=fonts["md"], fill=(255, 255, 255))

    _draw_list_panel(draw, "Scanlists", scanlists, selected_scanlist, left_panel, fonts, (80, 220, 120))
    _draw_list_panel(draw, "Sites", sites, selected_site, right_panel, fonts, (60, 180, 255))

    rr(draw, save_btn, 10, fill=(80, 220, 120))
    draw.text((383, 13), "SAVE", font=fonts["md"], fill=(36, 50, 68))

    _draw_arrow_button(draw, (18, 262, 114, 302), "▲", fonts, (10, 16, 24), (255, 255, 255))
    _draw_arrow_button(draw, (126, 262, 222, 302), "▼", fonts, (10, 16, 24), (255, 255, 255))
    _draw_arrow_button(draw, (258, 262, 354, 302), "▲", fonts, (10, 16, 24), (255, 255, 255))
    _draw_arrow_button(draw, (366, 262, 462, 302), "▼", fonts, (10, 16, 24), (255, 255, 255))

    return img
