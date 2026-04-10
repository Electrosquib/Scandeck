from UI import Screen, ScanUI, MenuUI, ScanlistsUI, Touch, TuneUI
import RPi.GPIO as GPIO
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
from PIL import ImageDraw

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
if current_screen == "home":
    current_screen = "menu"

t = 0.0
touch_coords = None
touch_pending = False
touch_expires_at = 0.0
menu_selected_index = 0
running = True
touch_lock = threading.Lock()
touch_event = threading.Event()
activity_history = deque(maxlen=6)
last_activity = None
frame = None

# CONSTANTS
FPS = 20
TOUCH_INT_PIN = 17
TOUCH_LATCH_TIME = .18

SCAN_BTN = (10, 270, 110, 310)
SKIP_BTN = (120, 270, 240, 310)
REC_BTN = (250, 270, 350, 310)
MENU_BTN = (360, 270, 460, 310)

MENU_SCAN_BTN = (10, 8, 90, 42)
MENU_LISTS_TILE = (18, 60, 158, 180)
MENU_TILE_RECTS = [
    (18, 60, 158, 180),
    (168, 60, 308, 180),
    (318, 60, 458, 180),
    (18, 190, 158, 310),
    (168, 190, 308, 310),
    (318, 190, 458, 310),
]

SCANLISTS_BACK_BTN = (10, 8, 108, 42)
SCANLISTS_SAVE_BTN = (366, 8, 460, 42)
SCANLISTS_LIST_UP_BTN = (18, 262, 114, 302)
SCANLISTS_LIST_DOWN_BTN = (126, 262, 222, 302)
SCANLISTS_SITE_UP_BTN = (258, 262, 354, 302)
SCANLISTS_SITE_DOWN_BTN = (366, 262, 462, 302)

VOL_CHANGED = True
CHANGE_VOL_TIME = datetime.now()
VOLUME_OVERLAY_SECONDS = 1.0

MODULATION = "nbfm"
BW = 12.5e3
FREQ = 146.520

last_volume_percent = None

port = 8080
lcd = Screen.ST7796()

int_pin = Button(TOUCH_INT_PIN, pull_up=True, bounce_time=0.02)

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
    return [x, y]

def touch_worker():
    global touch_coords, touch_pending, touch_expires_at, running

    while running:
        touch_event.wait(0.05)
        touch_event.clear()

        if not running:
            break

        if not (touch_pending or not int_pin.value):
            continue

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

def consume_touch():
    global touch_coords, touch_expires_at

    with touch_lock:
        coords = touch_coords
        touch_coords = None
        touch_expires_at = 0.0

    return coords

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
            },
            f,
            indent=4,
        )

def get_menu_tile_index(x, y):
    for i, rect in enumerate(MENU_TILE_RECTS):
        if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
            return i
    return None

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
    global VOL_CHANGED, CHANGE_VOL_TIME
    VOL_CHANGED = True
    CHANGE_VOL_TIME = datetime.now()

def get_current_volume_percent():
    for control_name in ("PCM", "Master", "Speaker", "Digital"):
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
    current_screen = "scanner"
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
    global proc, running

    running = False

    if proc is not None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except Exception:
            pass

        try:
            proc.terminate()
        except Exception:
            pass

        try:
            proc.wait(timeout=2)
        except Exception:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                pass

        proc = None

    subprocess.run(["pkill", "-f", "gr-op25_repeater/apps/rx.py"], check=False)
    subprocess.run(["pkill", "-f", "op25"], check=False)

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
        rx_path,
        "--args", "rtl",
        "-N", "LNA:47",
        "-S", "2400000",
        "-X",
        "-O", "hw:MAX98357A", # or 'default'
        "-V", "-2", "-U",
        "-l", f"http:0.0.0.0:{port}",
        "-T", settings.TRUNK_FILE
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=base,
        stdout = subprocess.DEVNULL,
        stderr = subprocess.DEVNULL,
        start_new_session=True,
    )
    return proc

proc = start_scan()
signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)
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

        current_volume_percent = get_current_volume_percent()
        if current_volume_percent is not None and current_volume_percent != last_volume_percent:
            last_volume_percent = current_volume_percent
            VOL_CHANGED = True
            CHANGE_VOL_TIME = datetime.now()

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
                    current_screen = "menu"
                    save_state()
        if current_screen == "menu":
            frame = MenuUI.make_ui(menu_selected_index, t)
            if active_touch and active_touch[0] > MENU_SCAN_BTN[0] and active_touch[0] < MENU_SCAN_BTN[2] and active_touch[1] > MENU_SCAN_BTN[1] and active_touch[1] < MENU_SCAN_BTN[3]:  # menu SCAN button
                consume_touch()
                current_screen = "scanner"
                save_state()
            elif active_touch:  # menu tile press
                tile_index = get_menu_tile_index(active_touch[0], active_touch[1])
                if tile_index is not None:
                    consume_touch()
                    if tile_index == 0:  # scanlists tile
                        current_screen = "scanlists"
                        save_state()
        if current_screen == "scanlists":
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
                    current_screen = "menu"
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
        if current_screen == "tune":
            frame = TuneUI.make_ui(FREQ, MODULATION,  BW, t)
        if frame is not None:
            # Keep the volume overlay visible on every frame.
            visible_volume = current_volume_percent if current_volume_percent is not None else last_volume_percent
            if VOL_CHANGED:
                frame = draw_volume_overlay(frame, visible_volume if visible_volume is not None else 0)
            if VOL_CHANGED and (datetime.now() - CHANGE_VOL_TIME).total_seconds() >= VOLUME_OVERLAY_SECONDS:
                VOL_CHANGED = False
        if frame:
            lcd.show(frame)
            frame.save("ui_preview.png")

        t += 1/FPS
        time.sleep(1/FPS)

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
    GPIO.cleanup()
except Exception:
    pass

print("\nExiting...")
sys.exit(0)
