import csv
import subprocess, time, requests, os, signal
import json

frequencies = []

def get_p25_info(freq, device = "hackrf=0", port = 8080, timeout = 4.0):
    rx_path = "/home/scandeck-one/op25/op25/gr-op25_repeater/apps/rx.py"
    base = "/home/scandeck-one/op25/op25/gr-op25_repeater/apps"
    url = f"http://127.0.0.1:{port}/"
    freq_hz = f"{freq}e6"
    cmd = [
        rx_path,
        "--args", device,
        "-f", freq_hz,
        "-g", "65",
        "-N", "RF:14,IF:32,BB:26",
        "-S", "2400000",
        "-X",
        "-l", f"http:0.0.0.0:{port}"
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=base,
        stdout = subprocess.DEVNULL,
        stderr = subprocess.DEVNULL
    )
    time.sleep(3)
    start = time.time()
    try:
        while time.time() - start < timeout:
            try:
                r = requests.post(
                    url,
                    json = [{"command": "update", "arg1": 0, "arg2": 0}],
                    timeout = 1.0
                )
                print(r.json())
                r.raise_for_status()
                # msg = msg[0]
                print(msg)
                if msg.get("json_type") == "trunk_update":
                    tl = msg.get("top_line").split(" ")
                    nac = tl[1]
                    wacn = tl[3]
                    sysid = tl[5]
                    tsbks = tl[8]
                    data = {
                            "freq": freq,
                            "nac": nac,
                            "wacn": wacn,
                            "sysid": sysid,
                            "tsbks": tsbks,
                            "valid_p25": True
                        }
                    print(data)
                    if nac is not None:
                        return True, data
            except:
                pass
            time.sleep(0.3)
    finally:
        proc.terminate()
    return None



def parse_sites(filepath):
    sites = {}

    with open(filepath, 'r') as f:
        reader = csv.reader(f)

        header = next(reader)

        for row in reader:
            if not row:
                continue

            rfss = row[0]
            site_dec = row[1]
            site_hex = row[2]
            nac = row[3] if row[3] else None
            desc = row[4]
            county = row[5]
            lat = float(row[6])
            lon = float(row[7])
            rng = float(row[8])

            # everything after index 9 = frequencies
            raw_freqs = row[9:]

            freqs = []
            for fval in raw_freqs:
                if not fval:
                    continue

                is_cc = fval.endswith('c')
                freq = float(fval.replace('c', ''))

                freqs.append({
                    "freq": freq,
                    "control": is_cc
                })

            sites[desc] = {
                "rfss": rfss,
                "site_id": site_dec,
                "site_hex": site_hex,
                "nac": nac,
                "county": county,
                "lat": lat,
                "lon": lon,
                "range": rng,
                "freqs": freqs
            }

    return sites
info = []

print(get_p25_info(851.41250000))

# sites = parse_sites("trs_sites_10161.csv")
# for site in sites.values():
#     for freq in site['freqs']:
#         print(get_p25_info(851.41250000))
# with open("channel_info.json", mode="w") as f:
#     f.write(json.dumps(info))