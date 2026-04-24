from UI import Screen, ScanUI, MenuUI, ScanlistsUI, Touch, TuneUI, AdsbUI
import RPi.GPIO as GPIO
import math
import time
from gpiozero import Button
from signal import pause
import os
import subprocess
import signal
import sys
import requests
import settings
import json
import sqlite3
import utils
import threading
from collections import deque
from datetime import datetime
from PIL import ImageDraw, Image

def get_db_connection():
    conn = sqlite3.connect("scanlists.db", timeout=30)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn

# STATES
with open(settings.STATE_FILE, "r") as f:
    state = json.load(f)
current_screen = state.get("current_screen", "home")
current_scanlist = state.get("current_scanlist", None)
current_scanlist_name = state.get("current_scanlist_name", None)
current_site = state.get("current_site", None)

MODULATION = state.get("modulation", "FM")
BW = state.get("bw", 12.5e3)
FREQ = state.get("freq", 146.520)

if current_screen == "home":
    current_screen = "menu"

t = 0.0
touch_coords = None
touch_pending = False
touch_expires_at = 0.0
touch_block_until = 0.0
menu_selected_index = 0
adsb_selected_index = 0
adsb_aircraft = []
adsb_last_refresh = 0.0
adsb_proc = None
try:
    adsb_max_range_nm = max(1.0, float(state.get("adsb_max_range_nm", AdsbUI.MAX_RANGE_NM)))
except Exception:
    adsb_max_range_nm = AdsbUI.MAX_RANGE_NM
running = True
touch_lock = threading.Lock()
touch_event = threading.Event()
activity_history = deque(maxlen=6)
last_activity = None
frame = None
volume_overlay_until = 0.0
volume_overlay_percent = None
last_volume_poll = 0.0
alsa_volume_control = None
encoder_lock = threading.Lock()
encoder_last_state = 0
encoder_transition_sum = 0
encoder_thread = None

# CONSTANTS
FPS = 20
SP_SD_PIN = 26
TOUCH_INT_PIN = 17
ENC_SW_PIN = 24
ENC_DT_PIN = 23
ENC_CLK_PIN = 22

TOUCH_LATCH_TIME = 2
SCREEN_TOUCH_DELAY = 0.25
FREQ_KEY_PRESS_TIME = 0
LAST_TOUCH_TIME = 0
VOLUME_STEP_PERCENT = 5
VOLUME_OVERLAY_SECONDS = 1.5
VOLUME_POLL_SECONDS = 1.0

SCAN_BTN = (10, 270, 110, 310)
SKIP_BTN = (120, 270, 240, 310)
REC_BTN = (250, 270, 350, 310)
MENU_BTN = (360, 270, 460, 310)

MENU_SCAN_BTN = (10, 8, 90, 42)
MENU_TILE_RECTS = [
    (23, 66, 233, 176),
    (247, 66, 457, 176),
    (23, 190, 233, 300),
    (247, 190, 457, 300),
]
MENU_TOUCH_PAD = 16

SCANLISTS_BACK_BTN = (10, 8, 108, 42)
SCANLISTS_SAVE_BTN = (366, 8, 460, 42)
SCANLISTS_LIST_UP_BTN = (18, 262, 114, 302)
SCANLISTS_LIST_DOWN_BTN = (126, 262, 222, 302)
SCANLISTS_SITE_UP_BTN = (258, 262, 354, 302)
SCANLISTS_SITE_DOWN_BTN = (366, 262, 462, 302)

VOL_CHANGED = True
CHANGE_VOL_TIME = datetime.now()

BW_STEPS = [2500, 5000, 6250, 8000, 10000, 12500, 15000, 20000, 25000]
tune_input = TuneUI.format_frequency(FREQ)
tune_input_dirty = False
last_volume_percent = None

port = 8080

# Enable MAX98357A SP_SD (Active Low)
GPIO.setmode(GPIO.BCM)
GPIO.setup(SP_SD_PIN, GPIO.OUT)
GPIO.output(SP_SD_PIN, GPIO.HIGH)

lcd = Screen.ST7796()
Touch.reset_touch_controller()

int_pin = Button(TOUCH_INT_PIN, pull_up=True, bounce_time=0.02)

def detect_alsa_volume_control():
    global alsa_volume_control

    if alsa_volume_control is not None:
        return alsa_volume_control

    for control_name in ("PCM", "Master", "Speaker", "Digital"):
        try:
            result = subprocess.run(
                ["amixer", "get", control_name],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout:
                alsa_volume_control = control_name
                return alsa_volume_control
        except Exception:
            continue

    alsa_volume_control = "PCM"
    return alsa_volume_control


def get_current_volume_percent():
    control_name = detect_alsa_volume_control()
    candidate_controls = [control_name] + [name for name in ("PCM", "Master", "Speaker", "Digital") if name != control_name]

    for control_name in candidate_controls:
        try:
            result = subprocess.run(
                ["amixer", "get", control_name],
                capture_output=True,
                text=True,
                check=False,
            )
            output = result.stdout
            if result.returncode != 0 or not output:
                continue
            for token in output.split():
                if token.startswith("[") and token.endswith("%]"):
                    return max(0, min(100, int(token[1:-2])))
        except Exception:
            continue
    return None

last_volume_percent = get_current_volume_percent()
if last_volume_percent is None:
    last_volume_percent = 0
volume_overlay_percent = last_volume_percent

def touch_callback():
    global touch_pending
    touch_pending = True
    touch_event.set()
int_pin.when_pressed = touch_callback

def normalize_touch(tc):
    if not tc:
        return None

    x = max(0, min(479, 480 - tc[1]))
    y = max(0, min(319, tc[0]))
    x = 479 - x
    y = 319 - y
    return [x, y]

def touch_worker():
    global touch_coords, touch_pending, touch_expires_at, running

    while running:
        touch_event.wait(0.05)
        touch_event.clear()

        if not running:
            break

        tc = Touch.read_touch()
        touch_pending = False
        if tc:
            with touch_lock:
                touch_coords = normalize_touch(tc)
                touch_expires_at = time.monotonic() + TOUCH_LATCH_TIME

def update_touch():
    global touch_coords
    with touch_lock:
        if touch_coords and time.monotonic() > touch_expires_at:
            touch_coords = None
            print("h")

def consume_touch():
    global touch_coords, touch_expires_at

    with touch_lock:
        coords = touch_coords
        touch_coords = None
        touch_expires_at = time.monotonic() + SCREEN_TOUCH_DELAY

    return coords

def clear_touch_state(block_for_transition = False):
    global touch_pending, touch_coords, touch_expires_at, touch_block_until

    with touch_lock:
        touch_pending = False
        touch_coords = None
        # touch_expires_at = 0.0

    if block_for_transition:
        touch_block_until = time.monotonic() + SCREEN_TOUCH_DELAY
    else:
        touch_block_until = 0.0

def set_screen(screen_name):
    global current_screen, adsb_selected_index, adsb_last_refresh, proc, adsb_proc
    previous_screen = current_screen
    current_screen = screen_name

    if screen_name == "adsb":
        stop_scan()
        adsb_proc = start_adsb()
        adsb_selected_index = 0
        adsb_last_refresh = 0.0
    elif previous_screen == "adsb" and screen_name != "adsb":
        stop_adsb()
        proc = start_scan()

    clear_touch_state(block_for_transition = True)

def save_state():
    current_scanlist_name = None
    scanlists = load_scanlist_choices()
    if scanlists and current_scanlist is not None and 0 <= current_scanlist < len(scanlists):
        current_scanlist_name = scanlists[current_scanlist]["name"]

    with open(settings.STATE_FILE, "w") as f:
        json.dump(
            {
                "current_screen": current_screen,
                "current_scanlist": current_scanlist,
                "current_site": current_site,
                "current_scanlist_name": current_scanlist_name,
                "modulation": MODULATION,
                "bw": BW,
                "freq": FREQ,
                "adsb_max_range_nm": adsb_max_range_nm,
            },
            f,
            indent=4,
        )

def get_menu_tile_index(x, y):
    for i, rect in enumerate(MENU_TILE_RECTS):
        padded = (
            max(0, rect[0] - MENU_TOUCH_PAD),
            max(0, rect[1] - MENU_TOUCH_PAD),
            min(479, rect[2] + MENU_TOUCH_PAD),
            min(319, rect[3] + MENU_TOUCH_PAD),
        )
        if padded[0] <= x <= padded[2] and padded[1] <= y <= padded[3]:
            return i
    return None

def point_in_rect(point, rect):
    return rect[0] <= point[0] <= rect[2] and rect[1] <= point[1] <= rect[3]

def normalize_modulation_label(value):
    value = str(value).upper()
    if "AM" == value:
        return "AM"
    if "LSB" in value:
        return "LSB"
    if "USB" in value:
        return "USB"
    return "FM"

def sync_tune_input():
    global tune_input, tune_input_dirty
    tune_input = TuneUI.format_frequency(FREQ)
    tune_input_dirty = False

def try_apply_tune_input():
    global FREQ_KEY_PRESS_TIME, FREQ
    FREQ_KEY_PRESS_TIME = time.monotonic()
    if not tune_input or tune_input in {".", "-"} or tune_input.endswith("."):
        return
    try:
        value = float(tune_input)
    except ValueError:
        return
    if value > 0 and FREQ_KEY_PRESS_TIME - time.monotonic() < 3:
        FREQ = value

ADSB_RANGE_STEPS = [5.0, 10.0, 20.0, 40.0, 80.0, 160.0]


def adjust_adsb_range(step):
    global adsb_max_range_nm

    current_range = max(1.0, float(adsb_max_range_nm))
    closest_index = min(range(len(ADSB_RANGE_STEPS)), key=lambda i: abs(ADSB_RANGE_STEPS[i] - current_range))
    next_index = max(0, min(len(ADSB_RANGE_STEPS) - 1, closest_index + step))
    adsb_max_range_nm = float(ADSB_RANGE_STEPS[next_index])

def tune_receiver():
    global proc, FREQ, MODULATION, BW

    trunk_file = utils.make_trunk_file_for_tune(FREQ, MODULATION, BW)
    proc = start_scan()

def adjust_bandwidth(step):
    global BW

    current_bw = int(round(float(BW)))
    closest_index = min(range(len(BW_STEPS)), key = lambda i: abs(BW_STEPS[i] - current_bw))
    next_index = max(0, min(len(BW_STEPS) - 1, closest_index + step))
    BW = float(BW_STEPS[next_index])

def handle_tune_keypad(label):
    global tune_input, tune_input_dirty

    current_text = tune_input if tune_input_dirty else TuneUI.format_frequency(FREQ)

    if label == "DEL":
        tune_input = current_text[:-1]
        tune_input_dirty = True
        try_apply_tune_input()
        return

    if label == "·":
        if "." in current_text:
            return
        if not tune_input_dirty:
            current_text = ""
        tune_input = (current_text or "0") + "."
        tune_input_dirty = True
        return

    if not tune_input_dirty:
        current_text = ""

    if len(current_text.replace(".", "")) >= 8:
        return

    tune_input = current_text + label
    tune_input_dirty = True
    try_apply_tune_input()

def get_talkgroup_alpha_by_system(system_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT decimal, alpha FROM talkgroups WHERE system_id = ?",
        (system_id,),
    )
    tg_dict = {str(row[0]): row[1] for row in cur.fetchall()}
    conn.close()
    return tg_dict

def load_scanlist_choices():
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    systems = cur.execute(
        """
        SELECT id, name
        FROM systems
        ORDER BY name COLLATE NOCASE, id
        """
    ).fetchall()

    scanlists = []
    for system in systems:
        sites = cur.execute(
            """
            SELECT id, site_dec, site_hex, description
            FROM sites
            WHERE system_id = ?
            ORDER BY site_dec, id
            """,
            (system["id"],),
        ).fetchall()
        scanlists.append(
            {
                "id": system["id"],
                "name": system["name"],
                "sites": [
                    {
                        "id": site["id"],
                        "label": f'{site["description"]}',
                    }
                    for site in sites
                ],
            }
        )

    conn.close()
    return scanlists

def change_volume_handler():
    global VOL_CHANGED, CHANGE_VOL_TIME, volume_overlay_until
    VOL_CHANGED = True
    CHANGE_VOL_TIME = datetime.now()
    volume_overlay_until = time.monotonic() + VOLUME_OVERLAY_SECONDS


def set_current_volume_percent(volume_percent):
    control_name = detect_alsa_volume_control()
    try:
        subprocess.run(
            ["amixer", "-q", "set", control_name, f"{int(volume_percent)}%"],
            check=False,
        )
    except Exception:
        pass

def adjust_volume(step):
    global volume_overlay_percent, last_volume_percent

    current_volume = last_volume_percent if last_volume_percent is not None else 0
    target_volume = max(0, min(100, int(current_volume) + (step * VOLUME_STEP_PERCENT)))
    set_current_volume_percent(target_volume)
    last_volume_percent = target_volume
    volume_overlay_percent = target_volume
    change_volume_handler()

def initialize_encoder_state():
    global encoder_last_state, encoder_transition_sum

    GPIO.setup(ENC_CLK_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(ENC_DT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(ENC_SW_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    encoder_last_state = (GPIO.input(ENC_CLK_PIN) << 1) | GPIO.input(ENC_DT_PIN)
    encoder_transition_sum = 0

def poll_encoder_once():
    global encoder_last_state, encoder_transition_sum

    current_state = (GPIO.input(ENC_CLK_PIN) << 1) | GPIO.input(ENC_DT_PIN)
    if current_state == encoder_last_state:
        return

    transition = (encoder_last_state << 2) | current_state
    step_delta = {
        0x01: 1, 0x07: 1, 0x08: 1, 0x0E: 1,
        0x02: -1, 0x04: -1, 0x0B: -1, 0x0D: -1,
    }.get(transition, 0)

    encoder_last_state = current_state
    if step_delta == 0:
        return

    with encoder_lock:
        encoder_transition_sum += step_delta
        if encoder_transition_sum >= 4:
            encoder_transition_sum = 0
            adjust_volume(1)
        elif encoder_transition_sum <= -4:
            encoder_transition_sum = 0
            adjust_volume(-1)

def encoder_worker():
    while running:
        poll_encoder_once()
        time.sleep(0.001)

def handle_volume_state_poll():
    global last_volume_percent, last_volume_poll, volume_overlay_percent

    now = time.monotonic()
    if now - last_volume_poll < VOLUME_POLL_SECONDS:
        return

    last_volume_poll = now
    current_volume_percent = get_current_volume_percent()
    if current_volume_percent is None:
        return

    if current_volume_percent != last_volume_percent:
        last_volume_percent = current_volume_percent
        volume_overlay_percent = current_volume_percent
        change_volume_handler()

def get_visible_volume_percent():
    if volume_overlay_percent is not None:
        return volume_overlay_percent
    if last_volume_percent is not None:
        return last_volume_percent
    return get_current_volume_percent()

def draw_volume_overlay(frame, volume_percent):
    if volume_percent is None:
        volume_percent = 0

    draw = ImageDraw.Draw(frame)
    overlay_box = (300, 6, 472, 42)
    draw.rounded_rectangle(overlay_box, radius=10, fill=(10, 16, 24), outline=(36, 50, 68), width=2)

    speaker = MenuUI.load_icon("speaker.png", (24, 24))
    frame.paste(speaker, (308, 12), speaker)

    bar_x0 = 340
    bar_y0 = 16
    bar_x1 = 460
    bar_y1 = 32
    draw.rounded_rectangle((bar_x0, bar_y0, bar_x1, bar_y1), radius=7, fill=(18, 28, 40), outline=(36, 50, 68), width=1)

    inner_pad = 3
    fill_right_margin = 0
    fill_width = int((bar_x1 - bar_x0 - inner_pad * 2 - fill_right_margin) * (volume_percent / 100.0))
    if fill_width > 0:
        draw.rounded_rectangle(
            (bar_x0 + inner_pad, bar_y0 + inner_pad, bar_x0 + inner_pad + fill_width, bar_y1 - inner_pad),
            radius=5,
            fill=(80, 220, 120),
        )

    # draw.text((465, 8), f"{volume_percent}%", fill=(235, 240, 248))
    return frame

def resolve_selection_indexes(scanlists):
    global current_scanlist, current_site

    if not scanlists:
        current_scanlist = None
        current_site = None
        return

    if current_scanlist is not None and not (0 <= current_scanlist < len(scanlists)):
        matched_scanlist_index = next(
            (index for index, scanlist in enumerate(scanlists) if scanlist["id"] == current_scanlist),
            None,
        )
        current_scanlist = matched_scanlist_index

    if current_scanlist is None and current_scanlist_name:
        matched_scanlist_index = next(
            (index for index, scanlist in enumerate(scanlists) if scanlist["name"] == current_scanlist_name),
            None,
        )
        current_scanlist = matched_scanlist_index

    if current_scanlist is None:
        current_scanlist = 0

    sites = scanlists[current_scanlist]["sites"]
    if not sites:
        current_site = None
        return

    if current_site is not None and not (0 <= current_site < len(sites)):
        matched_site_index = next(
            (index for index, site in enumerate(sites) if site["id"] == current_site),
            None,
        )
        current_site = matched_site_index

    if current_site is None:
        current_site = 0

def clamp_selection(scanlists):
    global current_scanlist, current_site

    if not scanlists:
        current_scanlist = None
        current_site = None
        return

    resolve_selection_indexes(scanlists)

    current_scanlist = max(0, min(current_scanlist, len(scanlists) - 1))

    sites = scanlists[current_scanlist]["sites"]
    if not sites:
        current_site = None
        return

    if current_site is None:
        current_site = 0
    current_site = max(0, min(current_site, len(sites) - 1))

def get_scanlists_ui_data():
    scanlists = load_scanlist_choices()
    clamp_selection(scanlists)

    if not scanlists:
        return [], []

    site_rows = scanlists[current_scanlist]["sites"]
    return scanlists, site_rows

def get_current_site_name():
    scanlists = load_scanlist_choices()
    clamp_selection(scanlists)

    if not scanlists or current_scanlist is None or current_site is None:
        return ""

    sites = scanlists[current_scanlist]["sites"]
    if not sites or not (0 <= current_site < len(sites)):
        return ""

    return sites[current_site].get("label", "")

def get_current_site_location():
    scanlists = load_scanlist_choices()
    clamp_selection(scanlists)

    if not scanlists or current_scanlist is None or current_site is None:
        return None

    system_id = scanlists[current_scanlist]["id"]
    site_row = scanlists[current_scanlist]["sites"][current_site]
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    row = cur.execute(
        """
        SELECT description, lat, lon
        FROM sites
        WHERE id = ? AND system_id = ?
        """,
        (site_row["id"], system_id),
    ).fetchone()
    conn.close()

    if not row:
        return None

    try:
        lat = float(row["lat"])
        lon = float(row["lon"])
    except (TypeError, ValueError):
        return None

    if lat == 0.0 and lon == 0.0:
        return None

    return {
        "label": row["description"] or site_row.get("label", ""),
        "lat": lat,
        "lon": lon,
    }

def compute_distance_bearing(center_lat, center_lon, target_lat, target_lon):
    earth_radius_nm = 3440.065

    lat1 = math.radians(center_lat)
    lon1 = math.radians(center_lon)
    lat2 = math.radians(target_lat)
    lon2 = math.radians(target_lon)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    sin_dlat = math.sin(dlat / 2.0)
    sin_dlon = math.sin(dlon / 2.0)
    a = sin_dlat * sin_dlat + math.cos(lat1) * math.cos(lat2) * sin_dlon * sin_dlon
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    distance_nm = earth_radius_nm * c

    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    bearing_deg = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0

    return distance_nm, bearing_deg

def build_demo_adsb_aircraft(center=None):
    center_lat = center["lat"] if center else 21.3069
    center_lon = center["lon"] if center else -157.8583

    demo = [
        {"hex": "A1B2C3", "flight": "HAL123", "lat": center_lat + 0.12, "lon": center_lon - 0.08, "alt_baro": 3200, "gs": 145, "track": 78, "squawk": "4231"},
        {"hex": "D4E5F6", "flight": "N742AB", "lat": center_lat - 0.04, "lon": center_lon + 0.09, "alt_baro": 8600, "gs": 198, "track": 215, "squawk": "1200"},
        {"hex": "0A1B2C", "flight": "JST88", "lat": center_lat + 0.03, "lon": center_lon + 0.02, "alt_baro": 14100, "gs": 241, "track": 318, "squawk": "7421"},
        {"hex": "3D4E5F", "flight": "PAC16", "lat": center_lat - 0.16, "lon": center_lon - 0.11, "alt_baro": 4700, "gs": 122, "track": 163, "squawk": "7000"},
        {"hex": "7A8B9C", "flight": "AAL509", "lat": center_lat + 0.08, "lon": center_lon + 0.15, "alt_baro": 22100, "gs": 312, "track": 44, "squawk": "6104"},
    ]
    return demo

def resolve_adsb_feed_file():
    repo_root = os.path.dirname(os.path.abspath(__file__))
    feed_path = getattr(settings, "ADSB_FEED_FILE", "/home/scandeck-one/Scandeck/aircraft.json")

    if os.path.isdir(feed_path):
        return os.path.join(feed_path, "aircraft.json")

    feed_dir = getattr(settings, "ADSB_JSON_DIR", os.path.dirname(feed_path))
    if os.path.isdir(feed_dir) or not os.path.splitext(feed_path)[1]:
        return os.path.join(feed_dir, "aircraft.json")

    return feed_path

def load_adsb_aircraft():
    feed_url = getattr(settings, "ADSB_FEED_URL", "").strip()
    feed_path = resolve_adsb_feed_file()
    center = get_current_site_location()
    adsb_running = adsb_proc is not None

    raw = None
    if feed_url:
        try:
            r = requests.get(feed_url, timeout=1.0)
            r.raise_for_status()
            raw = r.json()
        except Exception as exc:
            print(f"adsb: unable to fetch feed: {exc}")
    if raw is None and os.path.exists(feed_path):
        try:
            with open(feed_path, "r") as f:
                raw = json.load(f)
        except Exception as exc:
            print(f"adsb: unable to read feed file: {exc}")

    items = []
    if isinstance(raw, dict):
        items = raw.get("aircraft", raw.get("planes", []))
    elif isinstance(raw, list):
        items = raw

    if not items and not adsb_running:
        items = build_demo_adsb_aircraft(center)

    output = []
    for item in items:
        if not isinstance(item, dict):
            continue

        lat = item.get("lat")
        lon = item.get("lon")
        distance_nm = item.get("distance_nm")
        bearing_deg = item.get("bearing_deg")

        if center and lat is not None and lon is not None:
            try:
                distance_nm, bearing_deg = compute_distance_bearing(center["lat"], center["lon"], float(lat), float(lon))
            except Exception:
                pass

        output.append(
            {
                "hex": str(item.get("hex", item.get("icao24", ""))).upper(),
                "callsign": str(item.get("flight", item.get("callsign", item.get("reg", item.get("hex", "UNKNOWN"))))).strip() or "UNKNOWN",
                "altitude": item.get("alt_baro", item.get("alt_geom", item.get("alt"))),
                "speed": item.get("gs", item.get("velocity")),
                "heading": item.get("track", item.get("heading")),
                "squawk": item.get("squawk", "-"),
                "lat": lat,
                "lon": lon,
                "distance_nm": distance_nm,
                "bearing_deg": bearing_deg,
                "x": item.get("x"),
                "y": item.get("y"),
                "range_nm": item.get("range_nm"),
            }
        )

    output.sort(
        key=lambda p: (
            float(p.get("distance_nm") or 9999.0),
            str(p.get("callsign", "")),
        )
    )
    return output, center

def apply_scan_selection(scanlists):
    global freq, proc, current_screen, current_scanlist_name, current_site, current_scanlist

    if not scanlists or current_scanlist is None or current_site is None:
        return

    selected_scanlist_row = scanlists[current_scanlist]
    selected_site_row = selected_scanlist_row["sites"][current_site]
    system_id = selected_scanlist_row["id"]
    site_id = selected_site_row["id"]
    freqs = utils.get_site_frequencies(system_id, site_id, control_only=True)
    if not freqs:
        return

    freq = freqs[0]
    try:
        proc.terminate()
        proc.wait(timeout=2)
    except Exception:
        pass
    set_screen("scanner")
    current_scanlist_name = selected_scanlist_row["name"]
    trunk_file = utils.make_trunk_file(system_id, site_id)
    proc = start_scan()
    save_state()

def demo_data():
    return {
        "system": "Honolulu Public Safety",
        "talkgroup": "12048",
        "alias": "DISPATCH EAST HI",
        "freq": "852.7125 MHz",
        "nac": "0x293",
        "site": "001-014",
        "wacn": "BEE00",
        "rssi": "-99",
        "signal": 4
    }

def parse_op25(data):
    out = {
        "freq": "-",
        "tgid": "-",
        "tag": "-",
        "srcaddr": "-",
        "srctag": "-",
        "encrypted": "-",
        "emergency": "-",
        "tdma": "-",
        "alias": "-",
        "wacn": "-",
        "sysid": "-",
        "nac": "-",
        "rfss": "-",
        "site": "-",
        "site_alias": "-",
        "system": "",
        "talkgroup": "-",
        "error": "-",
        "fine_tune": "-",
        "rssi": 0,
        "signal": 0
    }

    if not data:
        return out

    for d in data:
        t = d.get("json_type")

        if t == "change_freq":
            out["freq"] = str(d.get("freq"))
            out["tgid"] = str(d.get("tgid"))
            out['talkgroup'] = str(d.get("tgid"))
            out["tag"] = str(d.get("tag"))
            out['nac'] = str(d.get("nac"))

        elif t == "channel_update":
            chs = d.get("channels", [])
            if chs:
                ch = d.get(chs[0], {})
                out["srcaddr"] = ch.get("srcaddr")
                out["srctag"] = ch.get("srctag")
                out["encrypted"] = ch.get("encrypted")
                out["emergency"] = ch.get("emergency")
                out["tdma"] = ch.get("tdma")

        elif t == "trunk_update":
            out["encrypted"] = d.get("encrypted", out["encrypted"])
            out["srcaddr"] = d.get("srcaddr", out["srcaddr"])

            for k, v in d.items():
                if isinstance(v, dict):
                    out["wacn"] = v.get("wacn", out["wacn"])
                    out["sysid"] = v.get("sysid", out["sysid"])
                    out["nac"] = v.get("nac", out["nac"])
                    out["rfss"] = v.get("rfid", out["rfss"])
                    out["site"] = v.get("stid", out["site"])
                    out["system"] = v.get("system", out["system"])

        elif t == "rx_update":
            out["error"] = d.get("error")
            out["rssi"] = int(-120 + max(0, 60 - abs(out["error"]) / 10))
            out["signal"] = min(5, max(0, int((out["rssi"] + 120) / 10)))
            out["fine_tune"] = d.get("fine_tune")
        
        if out['alias'] == "?":
            out['alias'] = str(d.get("tgid"))
        if out['tgid'] == "None":
            out['alias'] = "-"
            out['talkgroup'] = "-"
    return out

def build_activity_entry(info):
    talkgroup = str(info.get("talkgroup", "-"))
    alias = str(info.get("alias", "-"))
    freq = str(info.get("freq", "-"))

    if talkgroup in ("-", "None", "") and alias in ("-", "", "None"):
        return None

    return {
        "talkgroup": "" if talkgroup in ("-", "None") else talkgroup,
        "alias": "" if alias in ("-", "None") else alias,
        "freq": "" if freq in ("-", "None") else freq,
    }

def update_activity_history(info):
    global last_activity

    current_activity = build_activity_entry(info)

    if current_activity is None:
        return

    if last_activity is None:
        last_activity = current_activity
        return

    if current_activity == last_activity:
        return

    if not activity_history or activity_history[0] != last_activity:
        activity_history.appendleft(last_activity)

    last_activity = current_activity

def shutdown(signum=None, frame=None):
    global proc, adsb_proc, running

    running = False
    clear_touch_state()

    proc = stop_process(proc)
    adsb_proc = stop_process(adsb_proc)

    subprocess.run(["pkill", "-f", "gr-op25_repeater/apps/rx.py"], check=False)
    subprocess.run(["pkill", "-f", "op25"], check=False)

def stop_process(child_proc):
    if child_proc is None:
        return None

    try:
        os.killpg(child_proc.pid, signal.SIGTERM)
    except Exception:
        pass

    try:
        child_proc.terminate()
    except Exception:
        pass

    try:
        child_proc.wait(timeout=2)
    except Exception:
        try:
            os.killpg(child_proc.pid, signal.SIGKILL)
        except Exception:
            pass

    return None

def stop_scan():
    global proc

    proc = stop_process(proc)

def stop_adsb():
    global adsb_proc

    adsb_proc = stop_process(adsb_proc)

def get_info(host = "127.0.0.1", port = 8080, channel = 0, timeout = 1.0):
    url = f"http://{host}:{port}/"
    payload = [{
        "command": "update",
        "arg1": 0,
        "arg2": channel
    }]
    try:
        r = requests.post(url, json = payload, timeout = timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def start_scan():
    rx_path = "/home/scandeck-one/Scandeck/op25/op25/gr-op25_repeater/apps/rx.py"
    base = "/home/scandeck-one/Scandeck/op25/op25/gr-op25_repeater/apps"
    url = f"http://127.0.0.1:{port}/"
    cmd = [
        "/usr/bin/python3",
        rx_path,
        "--args", "rtl=0",
        "-N", "LNA:47",
        "-S", "2400000",
        "-X",
        "-O", "hw:0,0",
        "-V", "-2", "-U",
        "-l", f"http:0.0.0.0:{port}",
        "-T", settings.TRUNK_FILE
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=base,
        stdout = subprocess.DEVNULL,
        stderr = None,
        start_new_session=True,
    )
    return proc

def start_adsb():
    repo_root = os.path.dirname(os.path.abspath(__file__))
    feed_path = resolve_adsb_feed_file()
    start_cmd = getattr(settings, "ADSB_START_CMD", None)
    cwd = getattr(settings, "ADSB_START_CWD", repo_root)
    json_dir = getattr(settings, "ADSB_JSON_DIR", os.path.dirname(feed_path))
    print(json_dir)
    if start_cmd is None:
        os.makedirs(json_dir, exist_ok=True)
        cmd = ["readsb", 
               "--write-json",
               json_dir,
                "--device-type", "rtlsdr",]
    else:
        cmd = list(start_cmd)

    try:
        return subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=None,
            start_new_session=True,
        )
    except FileNotFoundError:
        print(f"adsb: unable to start process, command not found: {cmd[0]}")
    except Exception as exc:
        print(f"adsb: unable to start process: {exc}")

    return None

proc = start_scan()
if current_screen == "adsb":
    stop_scan()
    adsb_proc = start_adsb()
signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)
initialize_encoder_state()
encoder_thread = threading.Thread(target=encoder_worker, name="encoder-worker", daemon=True)
encoder_thread.start()
touch_thread = threading.Thread(target=touch_worker, name="touch-worker", daemon=True)
touch_thread.start()

talkgroups = {}
if current_scanlist is not None:
    scanlists = load_scanlist_choices()
    if scanlists and 0 <= current_scanlist < len(scanlists):
        system_id = scanlists[current_scanlist]["id"]
        talkgroups = get_talkgroup_alpha_by_system(system_id)

while running:
    try:
        frame = None
        update_touch()
        with touch_lock:
            active_touch = touch_coords
        if time.monotonic() < touch_block_until:
            active_touch = None

        handle_volume_state_poll()

        if current_screen == "scanner":
            info = parse_op25(get_info())
            # info = demo_data()
            info['system'] = current_scanlist_name if current_scanlist_name else ""
            info['alias'] = talkgroups.get(info['talkgroup'], info['alias'])
            info["site_alias"] = get_current_site_name()
            update_activity_history(info)
            info["activity_history"] = list(activity_history)
            frame = ScanUI.make_ui(info, t)
            if active_touch and SCAN_BTN[1] < active_touch[1] and active_touch[1] < SCAN_BTN[3]:
                if active_touch[0] > SCAN_BTN[0] and active_touch[0] < SCAN_BTN[2]:  # SCAN button
                    consume_touch()
                    print("SCAN")
                elif active_touch[0] > SKIP_BTN[0] and active_touch[0] < SKIP_BTN[2]:  # SKIP button
                    consume_touch()
                    print("SKIP")
                elif active_touch[0] > REC_BTN[0] and active_touch[0] < REC_BTN[2]:  # REC button
                    consume_touch()
                    print("REC")
                elif active_touch[0] > MENU_BTN[0] and active_touch[0] < MENU_BTN[2]:  # MENU button
                    consume_touch()
                    set_screen("menu")
                    save_state()
        elif current_screen == "menu":
            frame = MenuUI.make_ui(menu_selected_index, t)
            if active_touch and active_touch[0] > MENU_SCAN_BTN[0] and active_touch[0] < MENU_SCAN_BTN[2] and active_touch[1] > MENU_SCAN_BTN[1] and active_touch[1] < MENU_SCAN_BTN[3]:  # menu SCAN button
                consume_touch()
                set_screen("scanner")
                save_state()
            elif active_touch:  # menu tile press
                tile_index = get_menu_tile_index(active_touch[0], active_touch[1])
                if tile_index is not None:
                    consume_touch()
                    if tile_index == 0:  # scan tile
                        set_screen("scanner")
                        save_state()
                    elif tile_index == 1:  # scanlist select tile
                        set_screen("scanlists")
                        save_state()
                    elif tile_index == 2:  # tune tile
                        clear_touch_state(block_for_transition=True)
                        set_screen("tune")
                        save_state()
                    elif tile_index == 3:  # ADS-B tile
                        set_screen("adsb")
                        save_state()
        elif current_screen == "scanlists":
            scanlists_data, site_rows = get_scanlists_ui_data()
            frame = ScanlistsUI.make_ui(
                scanlists=scanlists_data,
                selected_scanlist=current_scanlist or 0,
                sites=site_rows,
                selected_site=current_site or 0,
                t=t,
            )

            if active_touch:
                if active_touch[0] > SCANLISTS_BACK_BTN[0] and active_touch[0] < SCANLISTS_BACK_BTN[2] and active_touch[1] > SCANLISTS_BACK_BTN[1] and active_touch[1] < SCANLISTS_BACK_BTN[3]:  # BACK button
                    consume_touch()
                    set_screen("menu")
                    save_state()
                elif active_touch[0] > SCANLISTS_SAVE_BTN[0] and active_touch[0] < SCANLISTS_SAVE_BTN[2] and active_touch[1] > SCANLISTS_SAVE_BTN[1] and active_touch[1] < SCANLISTS_SAVE_BTN[3]:  # SAVE button
                    consume_touch()
                    apply_scan_selection(scanlists_data)
                elif active_touch[0] > SCANLISTS_LIST_UP_BTN[0] and active_touch[0] < SCANLISTS_LIST_UP_BTN[2] and active_touch[1] > SCANLISTS_LIST_UP_BTN[1] and active_touch[1] < SCANLISTS_LIST_UP_BTN[3]:  # scanlist up button
                    consume_touch()
                    if scanlists_data:
                        current_scanlist = ((current_scanlist or 0) - 1) % len(scanlists_data)
                        current_site = 0
                        save_state()
                elif active_touch[0] > SCANLISTS_LIST_DOWN_BTN[0] and active_touch[0] < SCANLISTS_LIST_DOWN_BTN[2] and active_touch[1] > SCANLISTS_LIST_DOWN_BTN[1] and active_touch[1] < SCANLISTS_LIST_DOWN_BTN[3]:  # scanlist down button
                    consume_touch()
                    if scanlists_data:
                        current_scanlist = ((current_scanlist or 0) + 1) % len(scanlists_data)
                        current_site = 0
                        save_state()
                elif active_touch[0] > SCANLISTS_SITE_UP_BTN[0] and active_touch[0] < SCANLISTS_SITE_UP_BTN[2] and active_touch[1] > SCANLISTS_SITE_UP_BTN[1] and active_touch[1] < SCANLISTS_SITE_UP_BTN[3]:  # site up button
                    consume_touch()
                    if site_rows:
                        current_site = ((current_site or 0) - 1) % len(site_rows)
                        save_state()
                elif active_touch[0] > SCANLISTS_SITE_DOWN_BTN[0] and active_touch[0] < SCANLISTS_SITE_DOWN_BTN[2] and active_touch[1] > SCANLISTS_SITE_DOWN_BTN[1] and active_touch[1] < SCANLISTS_SITE_DOWN_BTN[3]:  # site down button
                    consume_touch()
                    if site_rows:
                        current_site = ((current_site or 0) + 1) % len(site_rows)
                        save_state()
        elif current_screen == "adsb":
            if time.monotonic() - adsb_last_refresh > 1.0:
                adsb_aircraft, adsb_center = load_adsb_aircraft()
                adsb_last_refresh = time.monotonic()
            else:
                adsb_center = get_current_site_location()

            center_label = adsb_center["label"] if adsb_center else ""
            feed_age_s = max(0.0, time.monotonic() - adsb_last_refresh)
            frame = AdsbUI.make_ui(
                aircraft=adsb_aircraft,
                selected_index=adsb_selected_index,
                center_label=center_label,
                center=adsb_center,
                feed_age_s=feed_age_s,
                t=t,
                max_range_nm=adsb_max_range_nm,
            )

            if active_touch:
                if point_in_rect(active_touch, AdsbUI.BACK_BTN):
                    consume_touch()
                    set_screen("menu")
                    save_state()
                elif point_in_rect(active_touch, AdsbUI.ZOOM_OUT_BTN):
                    consume_touch()
                    adjust_adsb_range(1)
                    save_state()
                elif point_in_rect(active_touch, AdsbUI.ZOOM_IN_BTN):
                    consume_touch()
                    adjust_adsb_range(-1)
                    save_state()
                elif point_in_rect(active_touch, AdsbUI.SEL_UP_BTN):
                    consume_touch()
                    if adsb_aircraft:
                        adsb_selected_index = (adsb_selected_index - 1) % len(adsb_aircraft)
                elif point_in_rect(active_touch, AdsbUI.SEL_DOWN_BTN):
                    consume_touch()
                    if adsb_aircraft:
                        adsb_selected_index = (adsb_selected_index + 1) % len(adsb_aircraft)
                elif point_in_rect(active_touch, AdsbUI.LIST_BOX) and active_touch[1] >= AdsbUI.LIST_ROW_TOP:
                    row_index = (active_touch[1] - AdsbUI.LIST_ROW_TOP) // AdsbUI.LIST_ROW_HEIGHT
                    visible_rows = max(1, (AdsbUI.LIST_BOX[3] - AdsbUI.LIST_ROW_TOP) // AdsbUI.LIST_ROW_HEIGHT)
                    start = 0
                    if adsb_selected_index >= visible_rows:
                        start = adsb_selected_index - visible_rows + 1
                    absolute_index = start + int(row_index)
                    if 0 <= row_index < visible_rows and adsb_aircraft and absolute_index < len(adsb_aircraft):
                        adsb_selected_index = absolute_index
                        consume_touch()
        elif current_screen == "tune":
            freq_display = tune_input if tune_input_dirty else TuneUI.format_frequency(FREQ)
            frame = TuneUI.make_ui(FREQ, normalize_modulation_label(MODULATION), BW, t, freq_text = freq_display)
            if active_touch:
                if point_in_rect(active_touch, TuneUI.TUNE_MENU_BTN):
                    consume_touch()
                    sync_tune_input()
                    set_screen("menu")
                    save_state()
                else:
                    matched_touch = False

                    for label, rect in TuneUI.TUNE_MOD_BUTTONS:
                        if point_in_rect(active_touch, rect):
                            consume_touch()
                            MODULATION = label
                            matched_touch = True
                            break

                    if not matched_touch and point_in_rect(active_touch, TuneUI.TUNE_BW_UP_BTN):
                        consume_touch()
                        adjust_bandwidth(1)
                        matched_touch = True

                    if not matched_touch and point_in_rect(active_touch, TuneUI.TUNE_BW_DOWN_BTN):
                        consume_touch()
                        adjust_bandwidth(-1)
                        matched_touch = True

                    if not matched_touch:
                        for label, rect in TuneUI.TUNE_KEYPAD_BUTTONS:
                            if point_in_rect(active_touch, rect):
                                consume_touch()
                                handle_tune_keypad(label)
                                matched_touch = True
                                break
        if frame is not None:
            visible_volume = get_visible_volume_percent()
            if VOL_CHANGED:
                frame = draw_volume_overlay(frame, visible_volume if visible_volume is not None else 0)
            if VOL_CHANGED and (time.monotonic() >= volume_overlay_until):
                VOL_CHANGED = False
        if frame:
            frame = frame.transpose(Image.ROTATE_180)
            lcd.show(frame) # CHANGE THIS!!
            frame.save("ui_preview.png")

        t += 1/FPS
        # time.sleep(1/FPS)

    except KeyboardInterrupt:
        shutdown()

try:
    touch_event.set()
    if "touch_thread" in globals():
        touch_thread.join(timeout=0.2)
except Exception:
    pass

try:
    int_pin.close()
except Exception:
    pass

try:
    if "encoder_thread" in globals():
        encoder_thread.join(timeout=0.2)
except Exception:
    pass

try:
    GPIO.cleanup()
except Exception:
    pass

print("\nExiting...")
sys.exit(0)
