import math
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "/home/scandeck-one/Scandeck/UI/fonts"
FONT_CACHE = {}

BACK_BTN = (10, 8, 108, 42)
RADAR_BOX = (10, 60, 192, 310)
ZOOM_OUT_BTN = (16, 258, 84, 302)
ZOOM_IN_BTN = (112, 258, 184, 302)
DETAIL_BOX = (202, 60, 470, 156)
LIST_BOX = (202, 166, 406, 310)
SEL_UP_BTN = (414, 172, 472, 240)
SEL_DOWN_BTN = (414, 245, 472, 310)
LIST_ROW_HEIGHT = 34
LIST_ROW_TOP = 172

MAX_RANGE_NM = 20.0


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


def fit_text(draw, text, font, max_width):
    text = "" if text is None else str(text)
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text

    trimmed = text
    while len(trimmed) > 1:
        trimmed = trimmed[:-1]
        candidate = trimmed + "..."
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            return candidate
    return "..."


def format_altitude(value):
    if value in (None, "", "-"):
        return "-"
    try:
        alt = int(round(float(value)))
    except Exception:
        return str(value)
    return f"{alt:,} ft"


def format_speed(value):
    if value in (None, "", "-"):
        return "-"
    try:
        speed = int(round(float(value)))
    except Exception:
        return str(value)
    return f"{speed} kt"


def format_heading(value):
    if value in (None, "", "-"):
        return "-"
    try:
        heading = int(round(float(value))) % 360
    except Exception:
        return str(value)
    return f"{heading:03d}°"


def format_distance(value):
    if value in (None, "", "-"):
        return "-"
    try:
        dist = float(value)
    except Exception:
        return str(value)
    return f"{dist:.1f} nm"


def _project_lat_lon(lat, lon, heading_deg, speed_kt, seconds):
    try:
        lat = math.radians(float(lat))
        lon = math.radians(float(lon))
        heading = math.radians(float(heading_deg))
        speed_kt = max(0.0, float(speed_kt))
        seconds = max(0.0, float(seconds))
    except Exception:
        return None, None

    distance_nm = speed_kt * seconds / 900.0
    if distance_nm <= 0:
        return math.degrees(lat), math.degrees(lon)

    earth_radius_nm = 3440.065
    angular_distance = distance_nm / earth_radius_nm
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    sin_ad = math.sin(angular_distance)
    cos_ad = math.cos(angular_distance)

    new_lat = math.asin(sin_lat * cos_ad + cos_lat * sin_ad * math.cos(heading))
    new_lon = lon + math.atan2(
        math.sin(heading) * sin_ad * cos_lat,
        cos_ad - sin_lat * math.sin(new_lat),
    )
    return math.degrees(new_lat), ((math.degrees(new_lon) + 540.0) % 360.0) - 180.0


def normalize_aircraft(aircraft):
    out = []
    if not aircraft:
        return out

    for item in aircraft:
        if not isinstance(item, dict):
            continue

        callsign = str(
            item.get("flight")
            or item.get("callsign")
            or item.get("reg")
            or item.get("hex")
            or "UNKNOWN"
        ).strip()
        if not callsign:
            callsign = "UNKNOWN"

        out.append(
            {
                "hex": str(item.get("hex", "")).upper(),
                "callsign": callsign,
                "altitude": item.get("alt_baro", item.get("alt_geom", item.get("alt"))),
                "speed": item.get("gs", item.get("velocity")),
                "heading": item.get("track", item.get("heading")),
                "squawk": item.get("squawk", "-"),
                "lat": item.get("lat"),
                "lon": item.get("lon"),
                "distance_nm": item.get("distance_nm"),
                "bearing_deg": item.get("bearing_deg"),
                "x": item.get("x"),
                "y": item.get("y"),
                "range_nm": item.get("range_nm"),
                "icao": item.get("icao24", item.get("hex", "")),
                "type": item.get("type", item.get("category", "")),
            }
        )

    return out


def _radar_position(plane, radar_center, radar_radius, center=None, elapsed_s=0.0, max_range_nm=MAX_RANGE_NM):
    cx, cy = radar_center

    if center and plane.get("lat") is not None and plane.get("lon") is not None:
        try:
            lat = float(plane["lat"])
            lon = float(plane["lon"])
            heading = plane.get("heading")
            if heading is None:
                heading = plane.get("track")
            speed = plane.get("speed")
            if heading is not None and speed is not None and elapsed_s > 0:
                lat, lon = _project_lat_lon(lat, lon, heading, speed, elapsed_s)
            if lat is not None and lon is not None:
                distance_nm, bearing_deg = _compute_distance_bearing(center["lat"], center["lon"], lat, lon)
                scale = min(1.0, distance_nm / max_range_nm)
                radius = int(scale * radar_radius)
                bearing_rad = math.radians(bearing_deg)
                x = cx + int(math.sin(bearing_rad) * radius)
                y = cy - int(math.cos(bearing_rad) * radius)
                return x, y
        except Exception:
            pass

    if plane.get("x") is not None and plane.get("y") is not None:
        try:
            x = float(plane["x"])
            y = float(plane["y"])
            return cx + int(x * radar_radius), cy + int(y * radar_radius)
        except Exception:
            pass

    distance_nm = plane.get("distance_nm")
    bearing_deg = plane.get("bearing_deg")

    if distance_nm is None or bearing_deg is None:
        return None

    try:
        distance_nm = max(0.0, float(distance_nm))
        bearing_deg = float(bearing_deg)
    except Exception:
        return None

    scale = min(1.0, distance_nm / max_range_nm)
    radius = int(scale * radar_radius)
    bearing_rad = math.radians(bearing_deg)
    x = cx + int(math.sin(bearing_rad) * radius)
    y = cy - int(math.cos(bearing_rad) * radius)
    return x, y


def _compute_distance_bearing(center_lat, center_lon, target_lat, target_lon):
    lat1 = math.radians(center_lat)
    lon1 = math.radians(center_lon)
    lat2 = math.radians(target_lat)
    lon2 = math.radians(target_lon)

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    sin_dlat = math.sin(dlat / 2.0)
    sin_dlon = math.sin(dlon / 2.0)
    a = sin_dlat * sin_dlat + math.cos(lat1) * math.cos(lat2) * sin_dlon * sin_dlon
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    distance_nm = 3440.065 * c

    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    bearing_deg = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    return distance_nm, bearing_deg


def _draw_radar(draw, radar_box, t, max_range_nm=MAX_RANGE_NM):
    x0, y0, x1, y1 = radar_box
    rr(draw, radar_box, 16, fill=(10, 16, 24), outline=(36, 50, 68), width=2)

    cx = (x0 + x1) // 2
    cy = (y0 + y1) // 2 + 6
    max_radius = min((x1 - x0) // 2 - 16, (y1 - y0) // 2 - 16)

    range_label = f"RANGE {int(round(max_range_nm))} NM"
    draw.text((x0 + 12, y0 + 10), range_label, font=safe_font(10, bold=True), fill=(120, 150, 180))

    for frac in (0.25, 0.5, 0.75, 1.0):
        r = int(max_radius * frac)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(28, 42, 58), width=1)

    draw.line((cx, y0 + 12, cx, y1 - 12), fill=(28, 42, 58), width=1)
    draw.line((x0 + 12, cy, x1 - 12, cy), fill=(28, 42, 58), width=1)

    sweep_angle = (t * 50.0) % 360.0
    sweep_rad = math.radians(sweep_angle)
    sx = cx + int(math.sin(sweep_rad) * max_radius)
    sy = cy - int(math.cos(sweep_rad) * max_radius)
    draw.line((cx, cy, sx, sy), fill=(80, 220, 120), width=2)
    draw.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill=(80, 220, 120))

    return cx, cy, max_radius


def _draw_zoom_controls(draw):
    rr(draw, ZOOM_OUT_BTN, 10, fill=(10, 16, 24), outline=(36, 50, 68), width=2)
    rr(draw, ZOOM_IN_BTN, 10, fill=(10, 16, 24), outline=(36, 50, 68), width=2)

    draw.text((ZOOM_OUT_BTN[0] + 22, ZOOM_OUT_BTN[1] + 6), "ZOOM", font=safe_font(9, bold=True), fill=(120, 150, 180))
    draw.text((ZOOM_IN_BTN[0] + 22, ZOOM_IN_BTN[1] + 6), "ZOOM", font=safe_font(9, bold=True), fill=(120, 150, 180))

    draw.text((ZOOM_OUT_BTN[0] + 28, ZOOM_OUT_BTN[1] + 16), "-", font=safe_font(22, bold=True), fill=(255, 255, 255))
    draw.text((ZOOM_IN_BTN[0] + 25, ZOOM_IN_BTN[1] + 16), "+", font=safe_font(22, bold=True), fill=(255, 255, 255))


def _draw_plane_marker(draw, pos, plane, selected=False):
    x, y = pos
    color = (160, 235, 255) if not selected else (60, 180, 255)
    halo = (80, 220, 120) if not selected else (110, 205, 255)
    heading = plane.get("heading")
    if heading is None:
        heading = plane.get("track")
    try:
        heading = float(heading)
    except Exception:
        heading = None

    if heading is not None:
        rad = math.radians(heading)
        tip_x = x + int(math.sin(rad) * 11)
        tip_y = y - int(math.cos(rad) * 11)
        base_left_x = x + int(math.sin(rad + math.radians(140)) * 6)
        base_left_y = y - int(math.cos(rad + math.radians(140)) * 6)
        base_right_x = x + int(math.sin(rad - math.radians(140)) * 6)
        base_right_y = y - int(math.cos(rad - math.radians(140)) * 6)
        draw.line((x, y, tip_x, tip_y), fill=halo, width=2)
        draw.polygon(
            [(tip_x, tip_y), (base_left_x, base_left_y), (base_right_x, base_right_y)],
            fill=halo,
        )

    draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=color, outline=(10, 16, 24))
    draw.ellipse((x - 10, y - 10, x + 10, y + 10), outline=halo, width=1)

    call = fit_text(draw, plane.get("callsign", "UNKNOWN"), safe_font(11, bold=True), 70)
    draw.text((x + 8, y - 8), call.upper(), font=safe_font(11, bold=True), fill=color)


def _draw_plane_list(draw, planes, selected_index, box):
    x0, y0, x1, y1 = box
    rr(draw, box, 16, fill=(14, 20, 30), outline=(36, 50, 68), width=2)
    title_font = safe_font(12)
    draw.text((x0 + 12, y0 + 10), "NEARBY AIRCRAFT", font=title_font, fill=(120, 150, 180))

    if not planes:
        draw.text((x0 + 12, y0 + 46), "No aircraft in range", font=safe_font(15), fill=(110, 130, 150))
        return

    visible_rows = max(1, (y1 - LIST_ROW_TOP) // LIST_ROW_HEIGHT)
    start = 0
    if selected_index >= visible_rows:
        start = selected_index - visible_rows + 1

    for row_offset, plane in enumerate(planes[start:start + visible_rows]):
        idx = start + row_offset
        row_y = LIST_ROW_TOP + row_offset * LIST_ROW_HEIGHT
        active = idx == selected_index
        bg = (60, 180, 255) if active else (18, 28, 40)
        fg = (10, 16, 24) if active else (235, 240, 248)
        rr(draw, (x0 + 8, row_y, x1 - 8, row_y + 28), 8, fill=bg, outline=None if active else (32, 46, 62), width=1)

        call = fit_text(draw, plane.get("callsign", "UNKNOWN"), safe_font(13, bold=True), 170)
        draw.text((x0 + 14, row_y + 7), call.upper(), font=safe_font(13, bold=True), fill=fg)
        summary = f"{format_altitude(plane.get('altitude'))}  {format_heading(plane.get('heading'))}  {format_distance(plane.get('distance_nm'))}"
        draw.text((x0 + 120, row_y + 9), fit_text(draw, summary, safe_font(9), 170), font=safe_font(9), fill=fg)


def _draw_selected_details(draw, plane, box):
    x0, y0, x1, y1 = box
    rr(draw, box, 16, fill=(14, 20, 30), outline=(36, 50, 68), width=2)
    title_font = safe_font(13)
    draw.text((x0 + 12, y0 + 10), "TRACKED TARGET", font=title_font, fill=(120, 150, 180))

    if not plane:
        draw.text((x0 + 12, y0 + 46), "Tap a plane to inspect", font=safe_font(15), fill=(110, 130, 150))
        return

    call = plane.get("callsign", "UNKNOWN")
    draw.text((x0 + 12, y0 + 30), fit_text(draw, call.upper(), safe_font(22, bold=True), 108), font=safe_font(22, bold=True), fill=(60, 180, 255))
    draw.text((x0 + 12, y0 + 60), fit_text(draw, f"HEX {plane.get('hex', '-')}", safe_font(10), 120), font=safe_font(10), fill=(120, 150, 180))
    draw.text((x0 + 12, y0 + 77), fit_text(draw, f"SQ {plane.get('squawk', '-')}", safe_font(10), 120), font=safe_font(10), fill=(120, 150, 180))

    stats = [
        ("ALT", format_altitude(plane.get("altitude"))),
        ("SPD", format_speed(plane.get("speed"))),
        ("HDG", format_heading(plane.get("heading"))),
        ("DIST", format_distance(plane.get("distance_nm"))),
    ]
    stat_x = x0 + 160
    stat_y = y0 + 10
    for idx, (label, value) in enumerate(stats):
        y = stat_y + idx * 20
        draw.text((stat_x, y), label, font=safe_font(10), fill=(120, 150, 180))
        draw.text((stat_x + 36, y), fit_text(draw, value, safe_font(12, bold=True), 92), font=safe_font(12, bold=True), fill=(235, 240, 248))


def make_ui(aircraft=None, selected_index=0, center_label="", center=None, feed_age_s=0.0, t=0, max_range_nm=MAX_RANGE_NM):
    planes = normalize_aircraft(aircraft)
    try:
        max_range_nm = max(1.0, float(max_range_nm))
    except Exception:
        max_range_nm = MAX_RANGE_NM

    if planes:
        selected_index = max(0, min(selected_index, len(planes) - 1))
        planes = sorted(
            planes,
            key=lambda p: (
                float(p.get("distance_nm") or 9999.0),
                str(p.get("callsign", "")),
            ),
        )
        selected_index = max(0, min(selected_index, len(planes) - 1))
    else:
        selected_index = 0

    img = Image.new("RGB", (480, 320), (8, 12, 18))
    draw = ImageDraw.Draw(img)

    header_font = safe_font(24, bold=True)
    sub_font = safe_font(12)

    draw.rectangle((0, 0, 480, 50), fill=(10, 16, 24))
    draw.line((0, 49, 480, 49), fill=(32, 46, 62), width=2)

    rr(draw, BACK_BTN, 10, fill=(10, 16, 24), outline=(36, 50, 68), width=2)
    draw.text((30, 15), "BACK", font=safe_font(18, bold=True), fill=(255, 255, 255))
    draw.text((188, 10), "ADS-B", font=header_font, fill=(235, 240, 248))
    draw.text((330, 12), f"{len(planes)} AIRCRAFT", font=sub_font, fill=(120, 150, 180))
    if center_label:
        draw.text((330, 27), fit_text(draw, center_label, sub_font, 130), font=sub_font, fill=(90, 110, 130))

    cx, cy, radar_radius = _draw_radar(draw, RADAR_BOX, t, max_range_nm=max_range_nm)

    for idx, plane in enumerate(planes):
        pos = _radar_position(
            plane,
            (cx, cy),
            radar_radius,
            center=center,
            elapsed_s=feed_age_s,
            max_range_nm=max_range_nm,
        )
        if pos is None:
            continue
        selected = idx == selected_index
        _draw_plane_marker(draw, pos, plane, selected=selected)

    _draw_zoom_controls(draw)

    selected_plane = planes[selected_index] if planes else None
    _draw_selected_details(draw, selected_plane, DETAIL_BOX)
    _draw_plane_list(draw, planes, selected_index, LIST_BOX)

    rr(draw, SEL_UP_BTN, 10, fill=(10, 16, 24), outline=(36, 50, 68), width=2)
    rr(draw, SEL_DOWN_BTN, 10, fill=(10, 16, 24), outline=(36, 50, 68), width=2)
    draw.text((433, 187), "▲", font=safe_font(24, bold=True), fill=(255, 255, 255))
    draw.text((433, 262), "▼", font=safe_font(24, bold=True), fill=(255, 255, 255))

    # if not planes:
    #     draw.text((24, 286), "No live ADS-B feed loaded. Drop aircraft JSON into the app or point it at dump1090/readsb.", font=safe_font(11), fill=(110, 130, 150))

    return img
