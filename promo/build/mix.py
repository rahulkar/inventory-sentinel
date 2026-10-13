"""Synthesize the SFX layer, then mix narration + Lyria score + SFX into the final soundtrack.

Cue times come from the CUE table in src/scenes1.js so picture and sound share one source of truth."""
import json, os, re, subprocess, wave
import numpy as np
import imageio_ffmpeg
from scipy.signal import butter, sosfilt

FF = imageio_ffmpeg.get_ffmpeg_exe()
HERE = os.path.dirname(os.path.abspath(__file__))
SR = 48000
DUR = 120.0
rng = np.random.default_rng(7)

js = open(os.path.join(HERE, "..", "src", "scenes1.js"), encoding="utf-8").read()
CUE = {k: float(v) for k, v in re.findall(r"(\w+):\s*([\d.]+)", js[js.index("const CUE"):js.index("};", js.index("const CUE"))])}
VO_START = {f"s{i}": CUE[f"s{i}"] for i in range(1, 10)}


# ---------------------------------------------------------------- dsp helpers
def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], btype="band", fs=SR, output="sos"), x)


def lp(x, f, order=2):
    return sosfilt(butter(order, f, btype="low", fs=SR, output="sos"), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, btype="high", fs=SR, output="sos"), x)


def env_ad(n, a, d):
    """attack (s) then exponential decay with time constant d (s)"""
    t = np.arange(n) / SR
    e = np.where(t < a, t / max(a, 1e-4), np.exp(-(t - a) / d))
    return e


def movavg(x, w):
    c = np.cumsum(np.concatenate([[0.0], x]))
    h = w // 2
    i = np.arange(len(x))
    lo = np.clip(i - h, 0, len(x)); hi = np.clip(i + h + 1, 0, len(x))
    return (c[hi] - c[lo]) / (hi - lo)


def norm(x, peak=1.0):
    m = np.max(np.abs(x)) + 1e-9
    return x / m * peak


def noise(n):
    return rng.standard_normal(n)


def sweep_sine(f0, f1, dur, curve="exp"):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f0 * (f1 / f0) ** (t / dur) if curve == "exp" else f0 + (f1 - f0) * t / dur
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


# ---------------------------------------------------------------- sounds (mono, peak ~1)
def s_pop(pitch=520):
    n = int(0.16 * SR)
    x = sweep_sine(pitch * 1.9, pitch, 0.16) * env_ad(n, 0.003, 0.045)
    x += 0.25 * bp(noise(n), 2000, 7000) * env_ad(n, 0.001, 0.006)
    return norm(x)


def s_poof():
    n = int(0.55 * SR)
    x = noise(n)
    out = np.zeros(n)
    for i, f in enumerate(np.linspace(3200, 500, 6)):
        seg = slice(i * n // 6, (i + 1) * n // 6)
        out[seg] = lp(x, f)[seg]
    out *= env_ad(n, 0.012, 0.14)
    out += 0.4 * sweep_sine(300, 140, 0.55) * env_ad(n, 0.005, 0.08)
    return norm(out)


def s_whoosh(dur=0.8):
    n = int(dur * SR)
    t = np.arange(n) / n
    x = noise(n)
    centre = 350 + 2400 * np.sin(np.pi * t) ** 2
    out = np.zeros(n)
    blocks = 24
    for i in range(blocks):
        seg = slice(i * n // blocks, (i + 1) * n // blocks)
        c = centre[(i * n // blocks)]
        out[seg] = bp(x, c * 0.6, c * 1.5)[seg]
    e = np.sin(np.pi * t) ** 1.6
    return norm(out * e)


def s_click():
    n = int(0.05 * SR)
    x = bp(noise(n), 1500, 6000) * env_ad(n, 0.0005, 0.004)
    x += 0.5 * np.sin(2 * np.pi * 1800 * np.arange(n) / SR) * env_ad(n, 0.0005, 0.01)
    return norm(x)


def s_plug():
    n = int(0.3 * SR)
    x = np.zeros(n)
    c = s_click()
    x[: len(c)] += c
    x[int(0.035 * SR): int(0.035 * SR) + len(c)] += 0.7 * c
    x += 0.9 * np.sin(2 * np.pi * 85 * np.arange(n) / SR) * env_ad(n, 0.002, 0.07)
    return norm(x)


def s_bell(f, dur=1.6, bright=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for p, a, d in [(1, 1, 0.9), (2.0, 0.35, 0.5), (2.76, 0.5 * bright, 0.35), (5.4, 0.25 * bright, 0.18), (8.93, 0.12 * bright, 0.09)]:
        x += a * np.sin(2 * np.pi * f * p * t) * np.exp(-t / (d * dur / 1.6))
    x *= np.minimum(1, t / 0.002)
    return norm(x)


def s_sparkle():
    n = int(1.2 * SR)
    x = np.zeros(n)
    for i, f in enumerate([2093, 2637, 3136, 4186, 3520]):
        b = s_bell(f, 0.8, 0.6) * (0.9 - i * 0.1)
        o = int(i * 0.045 * SR)
        x[o: o + len(b)] += b[: n - o]
    return norm(x)


def s_coin():
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    x = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t / d) for f, a, d in [(3150, 1, 0.09), (4720, 0.7, 0.06), (6900, 0.5, 0.04), (2280, 0.4, 0.12)])
    x += 0.3 * bp(noise(n), 3000, 9000) * env_ad(n, 0.0005, 0.004)
    return norm(x)


def s_type():
    n = int(0.06 * SR)
    x = bp(noise(n), 1200, 5000) * env_ad(n, 0.0005, 0.008)
    x += 0.3 * np.sin(2 * np.pi * rng.uniform(300, 500) * np.arange(n) / SR) * env_ad(n, 0.0005, 0.012)
    return norm(x)


def s_stamp():
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * (70 + 60 * np.exp(-t / 0.02)) * t) * env_ad(n, 0.001, 0.09)
    x += 0.6 * lp(noise(n), 2500) * env_ad(n, 0.001, 0.03)
    return norm(x)


def s_page():
    n = int(0.28 * SR)
    t = np.arange(n) / SR
    x = bp(noise(n), 900, 5000) * (0.6 + 0.4 * np.sin(2 * np.pi * 38 * t)) * np.sin(np.pi * t / t[-1]) ** 0.7
    return norm(x)


def s_flutter(dur=0.8):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = lp(noise(n), 1400) * (0.5 + 0.5 * np.sin(2 * np.pi * 13 * t)) ** 2 * np.sin(np.pi * t / t[-1])
    return norm(x)


def s_tick():
    n = int(0.03 * SR)
    x = hp(noise(n), 2500) * env_ad(n, 0.0005, 0.005)
    return norm(x)


def s_pencil(dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = bp(noise(n), 1800, 7000, 1)
    strokes = np.zeros(n)
    pos = 0
    while pos < n:
        L = int(rng.uniform(0.06, 0.22) * SR)
        e = np.sin(np.linspace(0, np.pi, min(L, n - pos))) ** 0.8 * rng.uniform(0.5, 1.0)
        strokes[pos: pos + len(e)] = e
        pos += L + int(rng.uniform(0.01, 0.06) * SR)
    grit = 0.7 + 0.3 * np.abs(lp(noise(n), 60))
    body = 0.35 * bp(noise(n), 250, 900, 1)
    y = (x + body) * strokes * grit
    fade = np.minimum(1, np.minimum(t / 0.05, (t[-1] - t) / 0.08))
    return norm(y * fade)


def s_blip(f):
    n = int(0.09 * SR)
    t = np.arange(n) / SR
    return norm(np.sin(2 * np.pi * f * t) * env_ad(n, 0.002, 0.025))


def s_rise(dur=0.9):
    n = int(dur * SR)
    t = np.arange(n) / n
    x = noise(n)
    out = np.zeros(n)
    for i in range(20):
        seg = slice(i * n // 20, (i + 1) * n // 20)
        c = 400 * (8 ** (i / 20))
        out[seg] = bp(x, c * 0.7, c * 1.4)[seg]
    tone = sweep_sine(330, 990, dur) * 0.35
    return norm((out + tone) * np.sin(np.pi * t * 0.5) ** 1.5 * (1 - t ** 8))


def s_patter(dur):
    n = int(dur * SR)
    out = np.zeros(n)
    pos = 0
    while pos < n - 3000:
        c = lp(noise(2000), 900) * env_ad(2000, 0.001, 0.008)
        out[pos: pos + 2000] += c * rng.uniform(0.4, 1)
        pos += int(rng.uniform(0.07, 0.13) * SR)
    return norm(out)


# ---------------------------------------------------------------- event list
EV = []  # (time, mono_signal, gain_db, pan -1..1)


def ev(t, sig, db, pan=0.0):
    EV.append((t, sig, db, pan))


C = CUE
# A: drawing the shop, vanishing stock, the five culprits
ev(0.05, s_pencil(2.3), -27, -0.1)
for i in range(8):
    tv = C["vanish"] + i * 0.36
    ev(tv, s_poof(), -21, rng.uniform(-0.5, 0.5))
for i, k in enumerate(["theft", "till", "miscount", "shortdel", "typo"]):
    ev(C[k] - 0.08, s_pop(480 + i * 70), -17, -0.7 + i * 0.35)
ev(C["till"] + 0.3, s_type(), -24, -0.35); ev(C["till"] + 0.45, s_type(), -24, -0.35); ev(C["till"] + 0.6, s_type(), -24, -0.35)
ev(C["miscount"] + 0.5, s_pencil(0.5), -26, 0)
ev(C["shortdel"] - 0.05, s_whoosh(0.6), -27, 0.35)
ev(C["typo"] + 0.1, s_pencil(0.4), -26, 0.7); ev(C["typo"] + 0.55, s_pencil(0.2), -24, 0.7)
# pans
for tp in [12.05, 18.9, 29.6, 43.4, 49.2, 58.9, 68.55, 88.8, 104.3]:
    ev(tp - 0.05, s_whoosh(0.85), -19, 0.0)
# B
ev(C["pct"] - 0.02, s_pop(400), -16, -0.4)
ev(C["pct"] + 0.35, s_pencil(0.6), -25, -0.4)
for i in range(14):
    t0 = C["s2"] + 0.3 + i * 0.42 + 0.35
    if t0 < 18.9:
        ev(t0, s_coin(), -27 - (i % 3) * 2, -0.4)
for i in range(5):
    ev(C["weeks"] + i * 0.24, s_page(), -24, 0.35)
ev(C["ifatall"] + 0.05, s_pop(300), -18, 0.4)
# C
ev(C["s3"] - 0.1, s_flutter(0.95), -20, 0.4)
ev(C["s3"] + 0.8, s_stamp(), -24, -0.4)
ev(C["s3"] + 0.82, s_sparkle(), -22, -0.4)
ev(C["name"], s_pencil(1.4), -26, 0.1)
for r, key in enumerate(["item", "store", "day"]):
    n = [12, 9, 14][r]
    for i in range(n):
        ev(C[key] + i * 0.035 + 0.25, s_tick(), -30, -0.2 + i / n * 0.7)
for i in range(3):
    ev(C["points"] + 0.25 + i * 0.25, s_bell(1046.5 * (1.0 if i < 2 else 1.26), 0.9), -24, 0.2 + i * 0.2)
ev(C["places"], s_patter(1.9), -30, 0.6)
# D
ev(C["plug"] - 0.2, s_pencil(1.3), -26, -0.4)
ev(C["speaks"], s_pop(560), -18, 0.5)
ev(C["connects"] + 2.4, s_plug(), -14, 0)
ev(C["connects"] + 2.42, s_sparkle(), -24, 0)
url_n = len("https://stock.yourco.com/mcp")
for i in range(url_n):
    ev(C["url"] + i / url_n * 1.0, s_type(), -27, -0.3)
ev(C["sync"] + 0.08, s_click(), -18, -0.2)
for i in range(30):
    ev(C["flow"] + i * 0.13, s_blip(float(rng.choice([784, 880, 1047, 1175, 1319, 1568]))), -31, rng.uniform(-0.4, 0.4))
ev(C["nomig"] - 0.03, s_stamp(), -15, -0.4)
ev(C["noreb"] - 0.03, s_stamp(), -15, 0)
for i in range(3):
    ev(C["agents"] - 0.6 + i * 0.3, s_pop(600 + i * 90), -20, 0.2 + i * 0.25)
    tp = C["agents"] + 0.55 + i * 0.72
    ev(tp, s_plug(), -17, 0.1 + i * 0.25)
    ev(tp, s_bell([1318.5, 1568, 2093][i], 0.8, 0.6), -26, 0.1 + i * 0.25)
# E
for i in range(40):
    ev(C["learns"] - 0.2 + rng.uniform(0, 1.5), s_tick(), -33, rng.uniform(-0.6, 0.2))
ev(C["learns"] + 1.3, s_whoosh(0.9), -29, -0.3)
for i in range(7):
    ev(C["learns"] + 2.2 + i * 0.05, s_bell(1568, 0.6, 0.5), -31, -0.2)
for i in range(3):
    ev(C["nolabels"] - 0.3 + i * 0.12 + 0.3, s_page(), -27, -0.5 + i * 0.3)
ev(C["nolabels"] + 0.55, s_pencil(0.5), -24, 0)
ev(C["nolabels"] + 1.05, s_poof(), -20, 0)
for i in range(16):
    ev(C["sixteen"] + 0.05 + i * 0.07, s_pop(420 * 2 ** (i / 16 * 1.0)), -24, 0.2 + (i % 4) * 0.15)
ev(C["voids"], s_pencil(0.5), -24, -0.3); ev(C["voids"] + 0.1, s_bell(1760, 0.6), -28, -0.3)
ev(C["afterhours"], s_pencil(0.5), -24, 0.3); ev(C["afterhours"] + 0.1, s_bell(1568, 0.6), -28, 0.3)
ev(C["compete"] + 0.35, s_click(), -18, -0.6)
ev(C["compete"] + 0.4, s_patter(3.0), -25, -0.2)
ev(C["winner"], s_sparkle(), -17, 0.0)
ev(C["winner"] + 0.15, s_pop(700), -20, 0.0)
ev(C["onepoint7"] + 0.1, s_rise(1.0), -22, 0.4)
ev(C["onepoint7"] + 0.6, s_stamp(), -17, 0.4)
ev(C["rule"] + 0.1, s_pencil(0.4), -25, 0.3)
# F (executive)
ev(C["lead"] - 0.3, s_pencil(1.2), -27, 0)
ev(C["lead"] + 0.7, s_pop(650), -22, 0.35)
ev(71.55, s_rise(1.15), -21, 0)
for i in range(3):
    ev(C["three"] + 0.15 + i * 0.3, s_pop(500 + i * 120), -19, -0.5 + i * 0.5)
for i in range(12):
    ev(C["varisk"] + i * 0.07, s_tick(), -29, -0.5)
ev(C["varisk"] + 0.9, s_pencil(0.35), -26, -0.5)
ev(C["visit"] + 0.05, s_bell(1318.5, 0.9), -24, 0)
ev(C["beats"] + 0.1, s_bell(1568, 1.0), -22, 0.5)
ev(C["beats"] + 0.25, s_bell(2093, 1.0), -25, 0.5)
for i in range(15):
    ev(C["where"] + i * 0.06, s_page(), -33, -0.4 + i / 30)
ev(C["where"] + 0.7, s_pencil(0.45), -25, -0.3)
for i in range(5):
    ev(C["first"] + 0.1 + i * 0.16, s_pop(700 + i * 50), -25, 0.4)
ev(C["first"] + 0.9, s_pencil(0.4), -26, 0.4)
ev(C["nostats"], s_page(), -20, 0.5)
ev(C["nostats"] + 0.05, s_pop(380), -20, 0.5)
ev(C["nostats"] + 0.45, s_pencil(0.35), -23, 0.5)
# G (chat + agents)
ev(C["question"] - 0.15, s_whoosh(0.5), -25, 0.6)
qn = 70
for i in range(qn):
    tt = C["question"] + 0.15 + i / qn * (C["ask"] - C["question"] - 0.3)
    if rng.random() < 0.8:
        ev(tt, s_type(), -28, 0.5)
ev(C["ask"], s_click(), -19, 0.5)
ev(C["ask"] + 0.2, s_pop(880), -19, 0.5)
for i in range(7):
    ev(C["team"] + i * 0.16, s_pop(440 * 2 ** (i / 7)), -21, -0.6 + i * 0.2)
ev(C["splits"] + 0.05, s_whoosh(0.7), -23, 0)
for t0, p in [(C["digs"] + 0.25, -0.2), (C["digs"] + 0.75, -0.2), (C["plans"] + 0.3, 0.3), (C["plans"] + 0.8, 0.3)]:
    ev(t0, s_pop(760), -21, p); ev(t0 + 0.02, s_click(), -26, p)
for i in range(18):
    ev(C["live"] + i * 0.2, s_blip(float(rng.choice([880, 1047, 1319, 1568]))), -32, rng.uniform(-0.3, 0.3))
ev(C["never"] - 0.1, s_pop(520), -18, -0.2)
ev(C["never"] + 1.0, s_pencil(0.4), -23, 0.7)
ev(C["never"] + 1.5, s_bell(1568, 0.8), -27, -0.4)
ev(C["change"] - 0.1, s_pop(600), -18, 0)
ev(C["yes"] + 0.65, s_click(), -14, 0.3)
ev(C["yes"] + 0.78, s_stamp(), -15, 0.3)
ev(C["yes"] + 0.8, s_bell(1318.5, 1.3), -21, 0.3); ev(C["yes"] + 0.95, s_bell(1975.5, 1.3), -23, 0.3)
# H
ev(C["close"] - 0.4, s_pencil(0.9), -27, 0)
for i in range(3):
    ev(C["close"] + 0.1 + i * 0.5, s_whoosh(0.6), -29, -0.4 + i * 0.4)
    ev(C["close"] + 0.1 + i * 0.5 + 1.45, s_pop(900 + i * 100), -25, 0)
ev(C["smarter"], s_flutter(0.3), -28, 0)
ev(C["smarter"] + 0.35, s_sparkle(), -17, 0)
# I
ev(C["s9"] - 0.6, s_page(), -16, 0); ev(C["s9"] - 0.55, s_whoosh(0.7), -24, 0)
ev(C["logo"] - 0.2, s_pop(520), -21, -0.5)
ev(C["logo"], s_pencil(1.4), -26, 0.1)
for i, k in enumerate(["plugin", "learn", "find"]):
    ev(C[k] - 0.1, s_pop(523.25 * [1, 1.26, 1.5][i]), -19, -0.4 + i * 0.4)
ev(C["before"], s_pencil(0.9), -25, 0)
ev(C["before"] + 1.45, s_sparkle(), -20, -0.4)


# ---------------------------------------------------------------- mix
def load_audio(path, sr=SR, ch=2):
    raw = subprocess.run([FF, "-loglevel", "error", "-i", path, "-ac", str(ch), "-ar", str(sr), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, ch).copy()


N = int(DUR * SR)
music = load_audio(os.path.join(HERE, "audio", "music", "m35a_1.mp3"))[:N]
music = np.pad(music, ((0, max(0, N - len(music))), (0, 0)))
vo = np.zeros(N)
for sid, t0 in VO_START.items():
    x = load_audio(os.path.join(HERE, "audio", "vo_proc", f"{sid}.wav"), ch=1)[:, 0]
    i0 = int(t0 * SR)
    vo[i0: i0 + len(x)] += x[: N - i0]
sfx = np.zeros((N, 2))
for t0, sig, db, pan in EV:
    i0 = int(t0 * SR)
    if i0 >= N:
        continue
    g = 10 ** (db / 20)
    L = np.cos((pan + 1) * np.pi / 4) * np.sqrt(2) * 0.7071
    R = np.sin((pan + 1) * np.pi / 4) * np.sqrt(2) * 0.7071
    n = min(len(sig), N - i0)
    sfx[i0: i0 + n, 0] += sig[:n] * g * L
    sfx[i0: i0 + n, 1] += sig[:n] * g * R
# a touch of room on the SFX so they sit in the same space
rev = np.zeros_like(sfx)
for d, a in [(0.023, 0.25), (0.041, 0.18), (0.067, 0.12), (0.097, 0.08)]:
    k = int(d * SR)
    rev[k:, 0] += sfx[:-k, 1] * a
    rev[k:, 1] += sfx[:-k, 0] * a
sfx = sfx + lp(rev.T, 5000).T * 0.8

# duck the music under the voice (smoothed envelope, fast attack, slow release)
hop = 480
e = np.sqrt(movavg(vo ** 2, hop))
env = np.zeros_like(e)
a_att, a_rel = np.exp(-1 / (0.03 * SR)), np.exp(-1 / (0.45 * SR))
lvl = 0.0
for i in range(0, len(e), 48):
    v = e[i]
    lvl = v + (lvl - v) * (a_att ** 48 if v > lvl else a_rel ** 48)
    env[i: i + 48] = lvl
speech = np.clip(env / 0.05, 0, 1)
# level-adaptive ducking: under speech, hold the score near a fixed RMS target so loud passages
# (the call-and-response section) never crowd the narrator; between lines it plays at its base level
mono = music.mean(axis=1)
win = int(0.4 * SR)
m_env = np.sqrt(movavg(mono ** 2, win)) + 1e-6
base = 10 ** (-3.5 / 20)
target = 10 ** (-31.0 / 20)
g_speech = np.clip(target / m_env, 10 ** (-22 / 20), base)
g = base + (g_speech - base) * speech
sm = int(0.25 * SR)
music_gain = movavg(g, sm)
# let the score breathe a little louder at the very start and the end card
music_gain *= 1 + 0.35 * np.clip(1 - np.arange(N) / (1.4 * SR), 0, 1)
mix = music * music_gain[:, None] + vo[:, None] * 10 ** (1.0 / 20) + sfx
# gentle master: soft clip, then a final fade
mix *= 0.8
mix = np.tanh(mix * 1.1) / np.tanh(1.1)
fade = np.ones(N)
f0 = int((DUR - 1.2) * SR)
fade[f0:] = np.linspace(1, 0, N - f0) ** 1.5
mix *= fade[:, None]
out_wav = os.path.join(HERE, "audio", "final_mix_raw.wav")
with wave.open(out_wav, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(mix, -1, 1) * 32767).astype(np.int16).tobytes())
# loudness-normalise for web playback (-15 LUFS, -1 dBTP), two passes
meas = subprocess.run([FF, "-hide_banner", "-i", out_wav, "-af", "loudnorm=I=-15:TP=-1.2:LRA=11:print_format=json", "-f", "null", "-"], capture_output=True, text=True).stderr
m = json.loads(meas[meas.rindex("{"):meas.rindex("}") + 1])
af = (f"loudnorm=I=-15:TP=-1.2:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
      f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample=48000")
final_wav = os.path.join(HERE, "audio", "final_mix.wav")
subprocess.run([FF, "-y", "-loglevel", "error", "-i", out_wav, "-af", af, "-ar", "48000", final_wav], check=True)
subprocess.run([FF, "-y", "-loglevel", "error", "-i", final_wav, "-c:a", "libmp3lame", "-b:a", "192k", os.path.join(HERE, "audio", "final_mix.mp3")], check=True)
print("events", len(EV), "measured", m["input_i"], "LUFS ->", "-15 LUFS")
