import numpy as np
# import ControlChannelScan.ControlChannelScan as Scan

def find_peaks(filename, samp_rate, center_freq, threshold_scale = 5, cluster_hz = 25e3, channel_step = 12.5e3, base_freq = 0):
    fft = np.fromfile(filename, dtype = np.float32)
    N = len(fft)
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
    out = []
    seen = set()
    for f, _ in selected:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out

bw = 2e6

scan_ranges = [
    (851e6, 869e6),
    (769e6, 775e6),
    (453e6, 470e6),
    (150e6, 174e6)
]

centers = []

for low, high in scan_ranges:
    f = low + bw / 2
    while f <= high - bw / 2:
        centers.append(f)
        f += bw * .8

print(len(centers))

freqs = find_peaks("fft.bin", 2e6, 851e6)
# print(freqs)
# print(len(freqs))