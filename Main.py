from UI import Screen, ScanUI, MenuUI, Touch
import RPi.GPIO as GPIO
import time
from gpiozero import Button
from signal import pause
import subprocess
import signal
import sys
import requests

# STATES
current_screen = "menu"
t = 0.0
touch_coords = []

# CONSTANTS
FPS = 20
TOUCH_INT_PIN = 17

SCAN_BTN = (10, 270, 110, 310)
SKIP_BTN = (120, 270, 240, 310)
REC_BTN = (250, 270, 350, 310)
MENU_BTN = (360, 270, 460, 310)

MENU_SCAN_BTN = (10, 8, 90, 42)

port = 8080
freq = 851.4125
lcd = Screen.ST7796()

int_pin = Button(TOUCH_INT_PIN, pull_up=True)

def touch_callback():
    global touch_coords
    tc = Touch.read_touch()
    if tc:
        touch_coords = [abs(tc[1] - 480), tc[0]]
int_pin.when_pressed = touch_callback

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

def shutdown(sig=None, frame=None):
    print("[-] Stopping...")
    proc.terminate()
    proc.wait()
    sys.exit(0)

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

def start_scan(control_channel_freq):
    rx_path = "/home/scandeck-one/Scandeck/op25/op25/gr-op25_repeater/apps/rx.py"
    base = "/home/scandeck-one/Scandeck/op25/op25/gr-op25_repeater/apps"
    url = f"http://127.0.0.1:{port}/"
    cmd = [
        rx_path,
        "--args", "rtl",
        "-f", f"{control_channel_freq}e6",
        "-N", "LNA:47",
        "-S", "2400000",
        "-X",
        "-O", "default",
        "-V", "-2", "-U",
        "-l", f"http:0.0.0.0:{port}"
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=base,
        stdout = subprocess.DEVNULL,
        stderr = subprocess.DEVNULL
    )
    return proc

proc = start_scan(freq)

while True:
    try:
        if current_screen == "scanner":
            info = parse_op25(get_info())
            # print(info)
            frame = ScanUI.make_ui(info, t)
            if touch_coords and SCAN_BTN[1] < touch_coords[1] and touch_coords[1] < SCAN_BTN[3]:
                if touch_coords[0] > SCAN_BTN[0] and touch_coords[0] < SCAN_BTN[2]:
                    print("SCAN")
                elif touch_coords[0] > SKIP_BTN[0] and touch_coords[0] < SKIP_BTN[2]:
                    print("SKIP")
                elif touch_coords[0] > REC_BTN[0] and touch_coords[0] < REC_BTN[2]:
                    print("REC")
                elif touch_coords[0] > MENU_BTN[0] and touch_coords[0] < MENU_BTN[2]:
                    current_screen = "menu"
        if current_screen == "menu":
            frame = MenuUI.make_ui(t)
            if touch_coords and touch_coords[0] > MENU_SCAN_BTN[0] and touch_coords[0] < MENU_SCAN_BTN[2] and touch_coords[1] > MENU_SCAN_BTN[1] and touch_coords[1] < MENU_SCAN_BTN[3]:
                current_screen = "scanner"

        lcd.show(frame)
        t += 1/FPS
        touch_coords = None
        time.sleep(1/FPS)

    except KeyboardInterrupt:
        proc.terminate()
        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)
        shutdown()
        print("\nExiting...")
        exit()