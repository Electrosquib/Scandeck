from UI import Scanner
import csv
import subprocess, time, requests, os, signal
import json
import signal, sys

port = 8080

def start_scan(control_channel_freq, device = "hackrf=0"):
    rx_path = "/home/scandeck-one/op25/op25/gr-op25_repeater/apps/rx.py"
    base = "/home/scandeck-one/op25/op25/gr-op25_repeater/apps"
    url = f"http://127.0.0.1:{port}/"
    cmd = [
        rx_path,
        "--args", device,
        "-f", f"{control_channel_freq}e6",
        "-g", "65",
        "-N", "RF:14,IF:32,BB:26",
        "-S", "2400000",
        "-X",
        "-O", "default",
        "-V",
        "-2",
        "-U",
        "-l", f"http:0.0.0.0:{port}"
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=base,
        stdout = subprocess.DEVNULL,
        stderr = subprocess.DEVNULL
    )
    return proc


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

def shutdown(sig=None, frame=None):
    print("[-] Stopping...")
    proc.terminate()
    proc.wait()
    sys.exit(0)

def parse_op25(data):
    out = {
        "freq": "?",
        "tgid": "?",
        "tag": "?",
        "srcaddr": "?",
        "srctag": "?",
        "encrypted": "?",
        "emergency": "?",
        "tdma": "?",
        "alias": "?",
        "wacn": "?",
        "sysid": "?",
        "nac": "?",
        "rfss": "?",
        "site": "?",
        "system": "?",
        "talkgroup": "?",
        "error": "?",
        "fine_tune": "?",
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
            out['alias'] = str(d.get("tag"))

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
            out["fine_tune"] = d.get("fine_tune")

    return out


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

proc = None
# try:
# 851.412
proc = start_scan(control_channel_freq = 851.4125)
time.sleep(3)

while True:
    info = parse_op25(get_info())
    Scanner.display(info)

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

# except Exception as e:
#     print(e)
#     shutdown()