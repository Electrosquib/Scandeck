import numpy as np
import ControlChannelScanDSP as Scan
import os
import time
import subprocess
import requests

url = "http://127.0.0.1:8080/"
bw = 2e6
scan_ranges = [
    (851e6, 869e6),
    (769e6, 775e6),
    (453e6, 470e6),
    (150e6, 174e6)
]
folder = "FFTs"
num_rescans = 2

centers = []
for low, high in scan_ranges:
    f = low + bw / 2
    while f <= high - bw / 2:
        centers.append(f)
        f += bw * .8

def find_peaks(filename, samp_rate, center_freq, threshold_scale = 5, cluster_hz = 25e3, channel_step = 12.5e3, base_freq = 0):
    fft = np.fromfile(filename, dtype = np.float32)
    N = len(fft)
    if N == 0:
        return []

    noise = np.median(fft)
    threshold = noise * threshold_scale

    candidates = np.where(
        (fft > threshold) &
        (fft > np.roll(fft, 1)) &
        (fft > np.roll(fft, -1))
    )[0]

    bin_width = samp_rate / N
    peaks = []

    for i in candidates:
        if i <= 0 or i >= N - 1:
            continue

        y0, y1, y2 = fft[i - 1], fft[i], fft[i + 1]
        denom = y0 - 2 * y1 + y2
        delta = 0 if denom == 0 else 0.5 * (y0 - y2) / denom

        peak_bin = i + delta
        freq = center_freq + (peak_bin - N // 2) * bin_width

        peaks.append((freq, y1))

    peaks.sort(key = lambda x: x[1], reverse = True)

    selected = []
    for f, p in peaks:
        if all(abs(f - sf) > cluster_hz for sf, _ in selected):
            f_locked = base_freq + round((f - base_freq) / channel_step) * channel_step
            selected.append((f_locked, p))

    selected.sort(key = lambda x: x[1], reverse = True)

    return selected

def combine_peak_lists(list_of_peak_lists):
    combined = []

    for peaks in list_of_peak_lists:
        combined.extend(peaks)

    combined.sort(key = lambda x: x[1], reverse = True)

    return combined

def subscan(center_freq, idx):
    scanner = Scan.ControlChannelScanDSP(freq=center_freq, num_bins=2048, scan_idx=idx)
    scanner.start()
    scanner.flowgraph_started.set()
    scanner.wait()

def rank_consensus(master_lists, tol = 12.5e3):
    clusters = []

    for peaks in master_lists:
        for f, mag in peaks:
            matched = False

            for c in clusters:
                if abs(f - c["freq"]) < tol:
                    c["freqs"].append(f)
                    c["mags"].append(mag)
                    c["count"] += 1
                    matched = True
                    break

            if not matched:
                clusters.append({
                    "freq": f,
                    "freqs": [f],
                    "mags": [mag],
                    "count": 1
                })

    results = []

    for c in clusters:
        avg_mag = sum(c["mags"]) / len(c["mags"])
        max_mag = max(c["mags"])

        score = (c["count"], avg_mag)

        results.append((c["freq"], avg_mag, c["count"], score))

    results.sort(key = lambda x: (x[3][0], x[3][1]), reverse = True)

    return results


def tune_and_check(freq, timeout = 2.0):
    # tune using hold (forces channel)
    requests.post(
        url,
        json=[{"command": "hold", "arg1": 0, "arg2": 0}],
        timeout=1.0
    )

    start = time.time()

    while time.time() - start < timeout:
        try:
            r = requests.post(
                url,
                json=[{"command": "update", "arg1": 0, "arg2": 0}],
                timeout=1.0
            )

            data = r.json()
            print(data)
            for msg in data:
                if msg.get("json_type") == "trunk_update":

                    nac = msg.get("nac")
                    sysid = msg.get("sysid")
                    wacn = msg.get("wacn")

                    return {
                        "freq": freq,
                        "nac": nac,
                        "wacn": wacn,
                        "sysid": sysid,
                        "valid_p25": True
                    }

        except:
            pass

        time.sleep(0.1)

    return None

peak_list = []
combined_peaks = []

def scan():
    scan_idx = 0
    for f in os.listdir(folder):
        path = os.path.join(folder, f)
        if os.path.isfile(path):
            os.remove(path)
    for i in range(num_rescans):
        for count, freq in enumerate(centers):
            subscan(freq, count)
            peak_list.append(find_peaks(f"FFTs/{count}.bin", 2e6, freq))
        combined_peaks.append(combine_peak_lists(peak_list))
        time.sleep(2)
    return rank_consensus(combined_peaks)

band_results = [[], [], [], []]
channels = []

if __name__ == "__main__":
    freqs = scan()
    for i in freqs:
        for count, ran in enumerate(scan_ranges):
            if ran[0] < i[0] and i[0] < ran[1]:
                band_results[count].append(i)
    for i in range(len(band_results)):
        band_results[i] = sorted(
            band_results[i],
            key = lambda x: (x[1]),
            reverse = True
        )

    # proc = subprocess.Popen(
    #     [
    #         "/home/scandeck-one/op25/op25/gr-op25_repeater/apps/rx.py",
    #         "--args", "hackrf=0",
    #         "-f", "851.4125e6",
    #         "-g", "65",
    #         "-N", "RF:14,IF:32,BB:26",
    #         "-S", "2400000",
    #         "-X",
    #         "-l", "http:0.0.0.0:8080"
    #     ],
    #     cwd="/home/scandeck-one/op25/op25/gr-op25_repeater/apps",
    #     stdout=subprocess.DEVNULL,
    #     stderr=subprocess.DEVNULL
    # )
    # time.sleep(3)

    # info = tune_and_check("851.4125e6")
    # if info:
    #     channels.append(info)
    #     print(info)
    # # else:
    # #     print(f"[-] {str(round(channel[0]/1e6, 4))+"e6"} NOT a P25 Channel")

    # for band in band_results:
    #     for channel in band[30:]:
    #         print(channel[0], channel[1])
    #     for channel in band:
    #         info = tune_and_check("851.4125e6")
    #         if info:
    #             channels.append(info)
    #             print(info)
    #         else:
    #             print(f"[-] {str(round(channel[0]/1e6, 4))+"e6"} NOT a P25 Channel")