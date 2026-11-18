#!/usr/bin/env python3
"""World news in one image -- Wednesday 18 November 2026.

Draws a 1024x1024 editorial news board with nothing but the Python standard
library: an anti-aliased vector stroke font, hand-drawn icons for each story
and a small PNG encoder. No network, no clock, no randomness: two runs give
byte-identical output.

Writes entry.png into $MAKEFUN_OUTPUT_DIR (default /output).
"""

import math
import os
import re
import struct
import zlib

W = H = 1024


# --------------------------------------------------------------------------
# Canvas
# --------------------------------------------------------------------------

def hexrgb(s):
    s = s.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def mix(c1, c2, t):
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c1, c2))


class Canvas:
    def __init__(self, w, h, bg):
        self.w, self.h = w, h
        self.px = bytearray(bytes(bg) * (w * h))

    # -- solid fills -------------------------------------------------------
    def rect(self, x0, y0, x1, y1, color):
        x0 = max(0, int(x0)); y0 = max(0, int(y0))
        x1 = min(self.w, int(x1)); y1 = min(self.h, int(y1))
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(color) * (x1 - x0)
        for y in range(y0, y1):
            i = (y * self.w + x0) * 3
            self.px[i:i + len(row)] = row

    def blend(self, idx, color, a):
        if a <= 0:
            return
        i = idx * 3
        p = self.px
        if a >= 1:
            p[i] = color[0]; p[i + 1] = color[1]; p[i + 2] = color[2]
            return
        b = 1.0 - a
        p[i] = int(p[i] * b + color[0] * a + 0.5)
        p[i + 1] = int(p[i + 1] * b + color[1] * a + 0.5)
        p[i + 2] = int(p[i + 2] * b + color[2] * a + 0.5)

    def apply(self, cov, color, alpha=1.0):
        for idx in sorted(cov):
            a = cov[idx]
            if a > 1:
                a = 1.0
            self.blend(idx, color, a * alpha)

    # -- anti-aliased primitives ------------------------------------------
    def circle_cov(self, cov, cx, cy, r):
        x0 = max(0, int(cx - r - 1)); x1 = min(self.w - 1, int(cx + r + 1))
        y0 = max(0, int(cy - r - 1)); y1 = min(self.h - 1, int(cy + r + 1))
        for y in range(y0, y1 + 1):
            dy = y + 0.5 - cy
            for x in range(x0, x1 + 1):
                dx = x + 0.5 - cx
                a = r + 0.5 - math.sqrt(dx * dx + dy * dy)
                if a > 0:
                    idx = y * self.w + x
                    if a > cov.get(idx, 0.0):
                        cov[idx] = a if a < 1 else 1.0

    def circle(self, cx, cy, r, color, alpha=1.0):
        cov = {}
        self.circle_cov(cov, cx, cy, r)
        self.apply(cov, color, alpha)

    def ring(self, cx, cy, r, width, color, a0=0.0, a1=360.0):
        pts = arc_points(cx, cy, r, r, a0, a1, step=4.0)
        self.polyline([pts], width, color)

    def seg_cov(self, cov, ax, ay, bx, by, r):
        x0 = max(0, int(min(ax, bx) - r - 1)); x1 = min(self.w - 1, int(max(ax, bx) + r + 1))
        y0 = max(0, int(min(ay, by) - r - 1)); y1 = min(self.h - 1, int(max(ay, by) + r + 1))
        dx = bx - ax; dy = by - ay
        l2 = dx * dx + dy * dy
        w = self.w
        rr = r + 0.5
        for y in range(y0, y1 + 1):
            cy = y + 0.5
            for x in range(x0, x1 + 1):
                cx = x + 0.5
                if l2 > 0:
                    t = ((cx - ax) * dx + (cy - ay) * dy) / l2
                    if t < 0:
                        t = 0.0
                    elif t > 1:
                        t = 1.0
                else:
                    t = 0.0
                ex = ax + t * dx - cx
                ey = ay + t * dy - cy
                a = rr - math.sqrt(ex * ex + ey * ey)
                if a > 0:
                    idx = y * w + x
                    if a > cov.get(idx, 0.0):
                        cov[idx] = a if a < 1 else 1.0

    def polyline(self, strokes, width, color, alpha=1.0, cov=None):
        own = cov is None
        if own:
            cov = {}
        r = width / 2.0
        for pts in strokes:
            if len(pts) == 1:
                pts = [pts[0], pts[0]]
            for i in range(len(pts) - 1):
                (ax, ay), (bx, by) = pts[i], pts[i + 1]
                self.seg_cov(cov, ax, ay, bx, by, r)
        if own:
            self.apply(cov, color, alpha)
        return cov

    def poly_cov(self, cov, pts, sub=4):
        ys = [p[1] for p in pts]
        y0 = max(0, int(math.floor(min(ys)))); y1 = min(self.h - 1, int(math.ceil(max(ys))))
        n = len(pts)
        inc = 1.0 / sub
        for y in range(y0, y1 + 1):
            row = {}
            for s in range(sub):
                sy = y + (s + 0.5) / sub
                xs = []
                for i in range(n):
                    x1_, y1_ = pts[i]
                    x2_, y2_ = pts[(i + 1) % n]
                    if (y1_ <= sy < y2_) or (y2_ <= sy < y1_):
                        xs.append(x1_ + (sy - y1_) * (x2_ - x1_) / (y2_ - y1_))
                xs.sort()
                for k in range(0, len(xs) - 1, 2):
                    xa = max(0.0, xs[k]); xb = min(float(self.w), xs[k + 1])
                    if xb <= xa:
                        continue
                    ia = int(xa); ib = int(xb)
                    if ia == ib:
                        row[ia] = row.get(ia, 0.0) + (xb - xa) * inc
                    else:
                        row[ia] = row.get(ia, 0.0) + (ia + 1 - xa) * inc
                        for x in range(ia + 1, ib):
                            row[x] = row.get(x, 0.0) + inc
                        if ib < self.w:
                            row[ib] = row.get(ib, 0.0) + (xb - ib) * inc
            base = y * self.w
            for x, a in row.items():
                idx = base + x
                if a > cov.get(idx, 0.0):
                    cov[idx] = a if a < 1 else 1.0

    def polygon(self, pts, color, alpha=1.0):
        cov = {}
        self.poly_cov(cov, pts)
        self.apply(cov, color, alpha)

    def rrect(self, x0, y0, x1, y1, r, color):
        """Rounded rectangle: solid body plus anti-aliased corners."""
        self.rect(x0 + r, y0, x1 - r, y1, color)
        self.rect(x0, y0 + r, x0 + r, y1 - r, color)
        self.rect(x1 - r, y0 + r, x1, y1 - r, color)
        for cx, cy, xa, ya in ((x0 + r, y0 + r, x0, y0), (x1 - r, y0 + r, x1 - r, y0),
                               (x0 + r, y1 - r, x0, y1 - r), (x1 - r, y1 - r, x1 - r, y1 - r)):
            for y in range(int(ya), int(ya + r)):
                for x in range(int(xa), int(xa + r)):
                    dx = x + 0.5 - cx; dy = y + 0.5 - cy
                    a = r + 0.5 - math.sqrt(dx * dx + dy * dy)
                    if a > 0:
                        self.blend(y * self.w + x, color, min(a, 1.0))

    # -- PNG ---------------------------------------------------------------
    def png(self):
        stride = self.w * 3
        raw = bytearray()
        prev = bytearray(stride)
        for y in range(self.h):
            line = self.px[y * stride:(y + 1) * stride]
            # filter 2 (Up) suits large flat areas; cheap and deterministic
            up = bytes((line[i] - prev[i]) & 0xFF for i in range(stride))
            raw.append(2)
            raw += up
            prev = line

        def chunk(tag, data):
            body = tag + data
            return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

        ihdr = struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0)
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def arc_points(cx, cy, rx, ry, a0, a1, step=8.0):
    n = max(2, int(abs(a1 - a0) / step) + 1)
    out = []
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        out.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
    return out


# --------------------------------------------------------------------------
# Stroke font. Units: cap height 10, y grows downward, baseline at y=10,
# x-height at y=4, descenders to y=13. Commands: M x y (new stroke),
# L x y (line), A cx cy rx ry a0 a1 (arc, degrees, 90 = down), | (break).
# --------------------------------------------------------------------------

GLYPHS = {
    "A": "M0 10 L3.5 0 L7 10 M1.3 6.6 L5.7 6.6",
    "B": "M0 5 L3.5 5 A3.5 2.5 2.4 2.5 90 -90 L0 0 L0 10 L3.6 10 A3.6 7.5 2.6 2.5 90 -90",
    "C": "A3.9 5 3.9 5 -42 -318",
    "D": "M0 0 L0 10 L2.4 10 A2.4 5 4.2 5 90 -90 L0 0",
    "E": "M5.6 0 L0 0 L0 10 L5.6 10 M0 5 L4.8 5",
    "F": "M5.6 0 L0 0 L0 10 M0 5 L4.8 5",
    "G": "A3.9 5 3.9 5 -42 -360 L4.4 5",
    "H": "M0 0 L0 10 M6 0 L6 10 M0 5 L6 5",
    "I": "M0 0 L0 10",
    "J": "M4.6 0 L4.6 7.6 A2.3 7.6 2.3 2.4 0 180",
    "K": "M0 0 L0 10 M6 0 L0 6.2 M2.1 4.1 L6.2 10",
    "L": "M0 0 L0 10 L5.2 10",
    "M": "M0 10 L0 0 L4 7.4 L8 0 L8 10",
    "N": "M0 10 L0 0 L6.4 10 L6.4 0",
    "O": "A4.2 5 4.2 5 0 360",
    "P": "M0 10 L0 0 L3.4 0 A3.4 2.7 2.6 2.7 -90 90 L0 5.4",
    "Q": "A4.2 5 4.2 5 0 360 | M4.8 7.2 L8.2 10.6",
    "R": "M0 10 L0 0 L3.4 0 A3.4 2.7 2.6 2.7 -90 90 L0 5.4 M3.2 5.4 L6.2 10",
    "S": "A3 2.5 2.8 2.5 -25 -270 A3 7.5 3 2.5 -90 155",
    "T": "M0 0 L6.4 0 M3.2 0 L3.2 10",
    "U": "M0 0 L0 7 A3 7 3 3 180 0 L6 0",
    "V": "M0 0 L3.5 10 L7 0",
    "W": "M0 0 L2.5 10 L5 1.5 L7.5 10 L10 0",
    "X": "M0 0 L6.4 10 M6.4 0 L0 10",
    "Y": "M0 0 L3.4 5.2 L6.8 0 M3.4 5.2 L3.4 10",
    "Z": "M0 0 L6 0 L0 10 L6.2 10",
    "a": "A2.8 7 2.8 3 0 360 | M5.6 4 L5.6 10",
    "b": "M0 0 L0 10 | A2.9 7 2.9 3 180 540",
    "c": "A3 7 3 3 -40 -320",
    "d": "A2.9 7 2.9 3 0 360 | M5.8 0 L5.8 10",
    "e": "M0.1 7 L5.8 7 A2.9 7 2.9 3 0 -315",
    "f": "M4.3 0.9 A3 2.2 1.7 1.8 -40 -180 L1.3 10 M0 4 L3.8 4",
    "g": "A2.9 7 2.9 3 0 360 | M5.8 4 L5.8 11 A2.9 11 2.9 2 0 160",
    "h": "M0 0 L0 10 M0 6.8 A2.9 6.8 2.9 2.8 180 360 L5.8 10",
    "i": "M0 4 L0 10 M0 1.4 L0 1.5",
    "j": "M1.4 4 L1.4 11.6 A0 11.6 1.4 1.4 0 140 M1.4 1.4 L1.4 1.5",
    "k": "M0 0 L0 10 M5 4 L0 8 M1.9 6.5 L5.1 10",
    "l": "M0 0 L0 10",
    "m": "M0 4 L0 10 M0 6.6 A2.25 6.6 2.25 2.6 180 360 L4.5 10 M4.5 6.6 A6.75 6.6 2.25 2.6 180 360 L9 10",
    "n": "M0 4 L0 10 M0 6.8 A2.9 6.8 2.9 2.8 180 360 L5.8 10",
    "o": "A3 7 3 3 0 360",
    "p": "M0 4 L0 13 | A2.9 7 2.9 3 180 540",
    "q": "A2.9 7 2.9 3 0 360 | M5.8 4 L5.8 13",
    "r": "M0 4 L0 10 M0 7 A3.4 7.2 3.4 3.2 180 282",
    "s": "A2.5 5.5 2.3 1.5 -20 -270 A2.5 8.5 2.5 1.5 -90 160",
    "t": "M1.3 1.6 L1.3 8.5 A2.8 8.5 1.5 1.5 180 55 M0 4 L3.8 4",
    "u": "M0 4 L0 7.2 A2.9 7.2 2.9 2.8 180 0 L5.8 4 M5.8 4 L5.8 10",
    "v": "M0 4 L2.75 10 L5.5 4",
    "w": "M0 4 L2 10 L4 4.6 L6 10 L8 4",
    "x": "M0 4 L5.4 10 M5.4 4 L0 10",
    "y": "M0 4 L2.9 10 M5.6 4 L2.4 12 L1.4 13 L0.4 13",
    "z": "M0 4 L5 4 L0 10 L5.1 10",
    "0": "A3 5 3 5 0 360",
    "1": "M0 2.2 L2.4 0 L2.4 10",
    "2": "A3 3 3 3 -165 30 L0 10 L6.1 10",
    "3": "A3 2.5 2.7 2.5 -150 90 A3 7.5 3 2.5 -90 150",
    "4": "M4.8 10 L4.8 0 L0 7 L6.5 7",
    "5": "M5.6 0 L1.2 0 L0.9 4.7 A3 6.9 3 3.1 -134 150",
    "6": "A3 7 3 3 0 360 | M0 7 A5.8 7 5.8 7 180 258",
    "7": "M0 0 L6 0 L2 10",
    "8": "A3 2.5 2.6 2.5 90 450 A3 7.5 3 2.5 -90 270",
    "9": "A3 3 3 3 0 360 | M6 3 A0.2 3 5.8 7 0 78",
    " ": "",
    ".": "M0 9.7 L0 9.8",
    ",": "M0.6 9.5 L0 11.6",
    ":": "M0 4.6 L0 4.7 M0 9.7 L0 9.8",
    ";": "M0.6 4.6 L0.6 4.7 M0.6 9.5 L0 11.6",
    "-": "M0 6.2 L3.4 6.2",
    "\u2013": "M0 6.2 L5 6.2",
    "\u2014": "M0 6.2 L8 6.2",
    "'": "M0 0 L0 2.8",
    "\u2019": "M0.6 0 L0 2.8",
    '"': "M0 0 L0 2.8 M1.8 0 L1.8 2.8",
    "(": "A3.2 5 3 6.2 238 122",
    ")": "A-1.4 5 3 6.2 -58 58",
    "/": "M4 -0.4 L0 10.4",
    "!": "M0 0 L0 7 M0 9.7 L0 9.8",
    "?": "A2.8 2.8 2.8 2.8 -160 60 L2.8 6.8 M2.8 9.7 L2.8 9.8",
    "+": "M0 6 L5 6 M2.5 3.5 L2.5 8.5",
    "%": "A1.4 1.8 1.4 1.8 0 360 | M0 10 L6.6 0 | A5.2 8.2 1.4 1.8 0 360",
    "\u00b7": "M0 6 L0 6.1",
    "&": "M7 10 L1.4 3.4 A2.9 2.3 1.5 2.3 145 -90 A2.9 2.3 1.5 2.3 -90 50 L0.6 7 A2.9 7.6 2.4 2.4 190 60 L6.2 6",
}

SPACE_W = 3.6
# glyphs whose descender hook may tuck under the previous letter (left bearing, units)
OVERHANG = {"j": 1.1}


def parse_glyph(src):
    toks = re.findall(r"[MLA|]|-?\d+(?:\.\d+)?", src)
    strokes, cur = [], None
    i = 0
    while i < len(toks):
        t = toks[i]
        if t == "M":
            cur = [(float(toks[i + 1]), float(toks[i + 2]))]
            strokes.append(cur)
            i += 3
        elif t == "L":
            cur.append((float(toks[i + 1]), float(toks[i + 2])))
            i += 3
        elif t == "A":
            cx, cy, rx, ry, a0, a1 = (float(v) for v in toks[i + 1:i + 7])
            pts = arc_points(cx, cy, rx, ry, a0, a1, step=7.5)
            if cur is None:
                cur = []
                strokes.append(cur)
            cur.extend(pts)
            i += 7
        elif t == "|":
            cur = None
            i += 1
        else:
            raise ValueError("bad glyph token %r" % t)
    xs = [p[0] for s in strokes for p in s]
    if xs:
        lo, hi = min(xs), max(xs)
        strokes = [[(x - lo, y) for x, y in s] for s in strokes]
        width = hi - lo
    else:
        width = SPACE_W
    return strokes, width


FONT = {ch: parse_glyph(src) for ch, src in GLYPHS.items()}


def glyph(ch):
    return FONT.get(ch) or FONT["?"]


def stroke_units(bold):
    return 1.75 if bold else 1.12


def advance(ch, bold, track=0.0):
    strokes, w = glyph(ch)
    if not strokes:
        return SPACE_W + track
    return w - OVERHANG.get(ch, 0.0) + stroke_units(bold) + 1.55 + track


def text_width(s, size, bold=False, track=0.0):
    k = size / 10.0
    total = sum(advance(c, bold, track) for c in s)
    if s:
        total -= 1.55 + track
    return total * k


def draw_text(cv, x, y, s, size, color, bold=False, track=0.0):
    """Draw string with cap-top at y. Returns the x after the last glyph."""
    k = size / 10.0
    sw = stroke_units(bold) * k
    half = sw / 2.0
    strokes_px = []
    pen = x + half
    for ch in s:
        strokes, _ = glyph(ch)
        ox = pen - OVERHANG.get(ch, 0.0) * k
        for st in strokes:
            strokes_px.append([(ox + gx * k, y + gy * k) for gx, gy in st])
        pen += advance(ch, bold, track) * k
    cv.polyline(strokes_px, sw, color)
    return pen


def wrap(s, size, maxw, bold=False):
    words = s.split()
    lines, cur = [], ""
    for wd in words:
        trial = (cur + " " + wd) if cur else wd
        if text_width(trial, size, bold) <= maxw or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def fit_wrap(s, size, maxw, max_lines, bold=False, min_size=8.0):
    while True:
        lines = wrap(s, size, maxw, bold)
        if (len(lines) <= max_lines and all(text_width(l, size, bold) <= maxw for l in lines)) \
                or size <= min_size:
            return lines, size
        size -= 0.5


# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------

BG = hexrgb("#F3EFE6")
NAVY = hexrgb("#0E1B36")
NAVY2 = hexrgb("#1B2F5A")
GOLD = hexrgb("#F2B33D")
WHITE = (255, 255, 255)
INK = hexrgb("#1A202C")
BODY = hexrgb("#3B4556")
MUTED = hexrgb("#6B7385")
CARD = hexrgb("#FFFFFF")
SHADOW = mix(BG, (0, 0, 0), 0.10)


# --------------------------------------------------------------------------
# Icons -- each draws inside a box (x, y, s, s)
# --------------------------------------------------------------------------

def icon_bg(cv, x, y, s, color):
    cv.rrect(x, y, x + s, y + s, 14, color)


def icon_summit(cv, x, y, s, accent):
    icon_bg(cv, x, y, s, mix(accent, WHITE, 0.82))
    # round table
    cx = x + s / 2
    pts = arc_points(cx, y + s * 0.80, s * 0.42, s * 0.12, 0, 360, 6)
    cv.polygon(pts, mix(accent, (0, 0, 0), 0.25))
    # three leaders: red (China), blue (USA), white-blue-red (Russia)
    people = ((x + s * 0.23, hexrgb("#1F4E9E")), (x + s * 0.5, hexrgb("#C8102E")),
              (x + s * 0.77, hexrgb("#4A5568")))
    for i, (px, col) in enumerate(people):
        top = y + s * (0.30 if i == 1 else 0.36)
        body = arc_points(px, top + s * 0.40, s * 0.15, s * 0.20, 180, 360, 6)
        cv.polygon(body, col)
        cv.circle(px, top + s * 0.08, s * 0.085, col)
    # three tiny flags on the table: USA, China, Russia
    fy = y + s * 0.72
    usx, cnx, rux = x + s * 0.23, x + s * 0.5, x + s * 0.77
    for j in range(6):
        cv.rect(usx - 9, fy + j * 2, usx + 9, fy + j * 2 + 2, hexrgb("#B22234" if j % 2 == 0 else "#FFFFFF"))
    cv.rect(usx - 9, fy, usx - 1, fy + 6, hexrgb("#3C3B6E"))
    cv.rect(cnx - 9, fy, cnx + 9, fy + 12, hexrgb("#DE2910"))
    for j, c in enumerate(("#FFFFFF", "#0039A6", "#D52B1E")):
        cv.rect(rux - 9, fy + j * 4, rux + 9, fy + j * 4 + 4, hexrgb(c))
    for fx in (usx, cnx, rux):
        cv.polyline([[(fx - 9, fy), (fx + 9, fy), (fx + 9, fy + 12), (fx - 9, fy + 12), (fx - 9, fy)]],
                    1.0, (90, 90, 90))
    cv.circle(cnx - 5, fy + 3.5, 2.2, hexrgb("#FFDE00"))


def icon_strike(cv, x, y, s, accent):
    icon_bg(cv, x, y, s, mix(accent, WHITE, 0.84))
    ground = y + s * 0.76
    cv.rect(x + 8, ground, x + s - 8, ground + 2, mix(accent, BODY, 0.5))
    # US base on the left: hangar and a flag pole
    gray = hexrgb("#4A5568")
    cv.rect(x + s * 0.12, ground - s * 0.10, x + s * 0.46, ground, gray)
    cv.polygon(arc_points(x + s * 0.29, ground - s * 0.10, s * 0.17, s * 0.10, 180, 360, 10), gray)
    cv.rect(x + s * 0.50, ground - s * 0.30, x + s * 0.52, ground, gray)
    for j in range(3):
        cv.rect(x + s * 0.52, ground - s * 0.30 + j * 3, x + s * 0.64, ground - s * 0.30 + j * 3 + 3,
                hexrgb("#C53030") if j != 1 else WHITE)
    cv.rect(x + s * 0.52, ground - s * 0.30, x + s * 0.57, ground - s * 0.30 + 5, hexrgb("#2C5282"))
    # incoming missile from the upper right, dashed trail behind it
    ex, ey = x + s * 0.40, y + s * 0.50          # missile nose
    sx, sy = x + s * 0.94, y + s * 0.10          # trail start
    for i in range(7):
        t0, t1 = i / 7.0, i / 7.0 + 0.08
        cv.polyline([[(sx + (ex - sx) * t0, sy + (ey - sy) * t0),
                      (sx + (ex - sx) * t1, sy + (ey - sy) * t1)]], 2.2, mix(accent, BODY, 0.3))
    ang = math.atan2(ey - sy, ex - sx)
    ca, sa = math.cos(ang), math.sin(ang)

    def rot(u, v):
        return (ex + u * ca - v * sa, ey + u * sa + v * ca)
    dark = hexrgb("#2D3748")
    cv.polygon([rot(-30, -4), rot(-6, -4), rot(0, 0), rot(-6, 4), rot(-30, 4)], dark)
    cv.polygon([rot(-30, -4), rot(-36, -11), rot(-24, -4)], dark)
    cv.polygon([rot(-30, 4), rot(-36, 11), rot(-24, 4)], dark)
    cv.polygon([rot(-34, -2.5), rot(-44, 0), rot(-34, 2.5)], hexrgb("#F6AD55"))
    # interception / impact burst above the hangar
    bx, by = x + s * 0.30, y + s * 0.56
    star = []
    for i in range(20):
        r = (s * 0.17) if i % 2 == 0 else (s * 0.075)
        a = math.radians(i * 18 - 90)
        star.append((bx + r * math.cos(a), by + r * math.sin(a)))
    cv.polygon(star, hexrgb("#F6AD55"), 0.92)
    cv.polygon([(bx + (p[0] - bx) * 0.55, by + (p[1] - by) * 0.55) for p in star], hexrgb("#E53E3E"))


def icon_bridge(cv, x, y, s, accent):
    icon_bg(cv, x, y, s, mix(hexrgb("#3182CE"), WHITE, 0.80))
    water = hexrgb("#2B6CB0")
    cv.rect(x + 1, y + s * 0.70, x + s - 1, y + s * 0.70 + 2, water)
    for row in range(3):
        wy = y + s * 0.78 + row * 9
        pts = [(x + 8 + i * 2, wy + 2.2 * math.sin((i * 2 + row * 7) / 5.0)) for i in range((s - 16) // 2)]
        cv.polyline([pts], 1.8, mix(water, WHITE, 0.25 * row))
    deck = hexrgb("#4A5568")
    dy = y + s * 0.38
    # left intact span with arch
    cv.rect(x + 6, dy, x + s * 0.36, dy + 6, deck)
    cv.ring(x + s * 0.21, dy + s * 0.20, s * 0.17, 3.0, deck, 200, 340)
    # right intact span with arch
    cv.rect(x + s * 0.70, dy, x + s - 6, dy + 6, deck)
    cv.ring(x + s * 0.85, dy + s * 0.20, s * 0.17, 3.0, deck, 200, 340)
    # piers
    for px in (x + s * 0.06, x + s * 0.36, x + s * 0.70, x + s * 0.94):
        cv.rect(px - 3, dy + 6, px + 3, y + s * 0.72, deck)
    # the collapsed middle span tilted into the water
    cv.polygon([(x + s * 0.38, dy + 8), (x + s * 0.43, dy + 4), (x + s * 0.66, y + s * 0.74),
                (x + s * 0.60, y + s * 0.78)], hexrgb("#C53030"))
    # crack marks
    cv.polyline([[(x + s * 0.37, dy - 8), (x + s * 0.40, dy - 2), (x + s * 0.37, dy + 2)],
                 [(x + s * 0.69, dy - 8), (x + s * 0.66, dy - 2), (x + s * 0.69, dy + 2)]], 2.0, hexrgb("#C53030"))


def icon_senate(cv, x, y, s, accent):
    icon_bg(cv, x, y, s, mix(accent, WHITE, 0.86))
    blue, red = hexrgb("#2B6CB0"), hexrgb("#C53030")
    cx, cy = x + s / 2, y + s * 0.70
    rows = [(s * 0.17, 12), (s * 0.25, 19), (s * 0.33, 27), (s * 0.41, 42)]   # 100 seats
    seats = []
    for r, n in rows:
        for i in range(n):
            a = math.pi - math.pi * i / (n - 1)
            seats.append((a, cx + r * math.cos(a), cy - r * math.sin(a)))
    seats.sort(key=lambda t: -t[0])          # sweep from the left
    for i, (_, sx, sy) in enumerate(seats):
        cv.circle(sx, sy, 3.1, blue if i < 56 else red)
    label = "56-44"
    tw = text_width(label, 15, True)
    draw_text(cv, cx - tw / 2, cy + 6, label, 15, INK, True)


def icon_virus(cv, x, y, s, accent):
    icon_bg(cv, x, y, s, mix(accent, WHITE, 0.84))
    cx, cy = x + s * 0.5, y + s * 0.5
    col = hexrgb("#2F855A")
    for i in range(12):
        a = math.radians(i * 30 + 15)
        r0, r1 = s * 0.22, s * 0.36
        cv.polyline([[(cx + r0 * math.cos(a), cy + r0 * math.sin(a)),
                      (cx + r1 * math.cos(a), cy + r1 * math.sin(a))]], 3.0, col)
        cv.circle(cx + r1 * math.cos(a), cy + r1 * math.sin(a), 5.5, hexrgb("#C53030"))
    cv.circle(cx, cy, s * 0.25, col)
    for dx, dy, r in ((-8, -6, 5), (9, -2, 4), (-2, 10, 6), (12, 12, 3)):
        cv.circle(cx + dx, cy + dy, r, mix(col, WHITE, 0.35))


def icon_voyager(cv, x, y, s, accent):
    space = hexrgb("#0B1430")
    cv.rrect(x, y, x + s, y + s, 14, space)
    seed = 1977
    for _ in range(26):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        sx = x + 6 + seed % (s - 12)
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        sy = y + 6 + seed % (s - 12)
        cv.circle(sx + 0.5, sy + 0.5, 0.9 + (seed % 3) * 0.35, (220, 225, 240))
    # the pale blue dot, far away, and the light-day link
    ex, ey = x + s * 0.16, y + s * 0.82
    cv.circle(ex, ey, 5, hexrgb("#63B3ED"))
    vx, vy = x + s * 0.62, y + s * 0.36
    for i in range(10):
        t0, t1 = i / 10.0, i / 10.0 + 0.05
        cv.polyline([[(ex + (vx - ex) * t0, ey + (vy - ey) * t0),
                      (ex + (vx - ex) * t1, ey + (vy - ey) * t1)]], 1.6, GOLD)
    # spacecraft: dish, bus and booms
    gray = hexrgb("#CBD5E0")
    cv.polyline([[(vx - 30, vy + 18), (vx + 30, vy - 10)], [(vx + 4, vy + 6), (vx + 16, vy + 30)]], 2.0, gray)
    cv.polygon([(vx - 6, vy - 2), (vx + 10, vy - 2), (vx + 10, vy + 12), (vx - 6, vy + 12)], hexrgb("#A0AEC0"))
    dish = arc_points(vx + 2, vy - 10, 22, 9, 0, 360, 8)
    cv.polygon(dish, (240, 242, 248))
    cv.polyline([dish], 1.4, hexrgb("#A0AEC0"))
    cv.circle(vx + 2, vy - 10, 2.5, hexrgb("#A0AEC0"))
    lab = "24 h"
    draw_text(cv, x + s - 8 - text_width(lab, 11, True), y + s - 20, lab, 11, GOLD, True)


def icon_cyclone(cv, x, y, s, accent):
    icon_bg(cv, x, y, s, mix(hexrgb("#3182CE"), WHITE, 0.82))
    cx, cy = x + s / 2, y + s / 2 - 4
    col = hexrgb("#DD6B20")
    for k in (0, 180):
        outer, inner = [], []
        for i in range(40):
            t = i / 39.0
            a = math.radians(k + 20 + t * 150)
            r = s * (0.13 + 0.27 * t)
            hw = s * 0.075 * (1 - t) + 0.6
            outer.append((cx + (r + hw) * math.cos(a), cy + (r + hw) * math.sin(a)))
            inner.append((cx + (r - hw) * math.cos(a), cy + (r - hw) * math.sin(a)))
        cv.polygon(outer + inner[::-1], col)
    cv.circle(cx, cy, s * 0.17, col)
    cv.circle(cx, cy, s * 0.07, mix(hexrgb("#3182CE"), WHITE, 0.82))
    lab = "CAT 5"
    draw_text(cv, x + s - 8 - text_width(lab, 11, True), y + s - 20, lab, 11, hexrgb("#9C4221"), True)


def icon_report(cv, x, y, s, accent):
    icon_bg(cv, x, y, s, mix(accent, WHITE, 0.86))
    px0, py0, px1, py1 = x + s * 0.22, y + s * 0.12, x + s * 0.70, y + s * 0.86
    cv.polygon([(px0 + 3, py0 + 4), (px1 + 3, py0 + 4), (px1 + 3, py1 + 4), (px0 + 3, py1 + 4)],
               mix(accent, (0, 0, 0), 0.15), 0.35)
    cv.polygon([(px0, py0), (px1 - 12, py0), (px1, py0 + 12), (px1, py1), (px0, py1)], WHITE)
    cv.polyline([[(px0, py0), (px1 - 12, py0), (px1, py0 + 12), (px1, py1), (px0, py1), (px0, py0)]],
                1.6, hexrgb("#718096"))
    for i in range(6):
        ly = py0 + 18 + i * 10
        cv.polyline([[(px0 + 8, ly), (px1 - 8 - (14 if i % 3 == 2 else 0), ly)]], 2.0, hexrgb("#A0AEC0"))
    # warning triangle over the corner
    tx, ty = x + s * 0.70, y + s * 0.66
    tri = [(tx, ty - 22), (tx + 22, ty + 16), (tx - 22, ty + 16)]
    cv.polygon(tri, hexrgb("#D69E2E"))
    cv.polyline([[(tx, ty - 8), (tx, ty + 4)], [(tx, ty + 10), (tx, ty + 10.2)]], 3.4, INK)


# --------------------------------------------------------------------------
# Stories of Wednesday 18 November 2026
# --------------------------------------------------------------------------

STORIES = [
    ("DIPLOMACY", "SHENZHEN, CHINA", "#2B6CB0", icon_summit,
     "Trump, Xi, Putin gather for APEC in Shenzhen",
     "Xi and Putin hold talks; Xi hugs Trump on arrival and Trump shakes Putin's hand. "
     "First three-way talks set for Thursday."),
    ("CONFLICT", "KUWAIT \u00b7 BAHRAIN", "#C53030", icon_strike,
     "Iran strikes at US bases in Kuwait and Bahrain",
     "Retaliation for US raid on Qeshm Island missile sites. Air defences intercept drones; "
     "Gulf stock markets fall."),
    ("WAR", "UKRAINE \u00b7 RUSSIA", "#B7791F", icon_bridge,
     "Kerch Bridge road span lies broken in the sea",
     "Footage shows 227 m arch in the sea after Ukrainian drone and missile strikes; "
     "rail line damaged but trains run."),
    ("POLITICS", "UNITED STATES", "#553C9A", icon_senate,
     "Democrat Mary Peltola wins Alaska Senate seat",
     "Ousts Republican Dan Sullivan, 9th midterm flip: Democrats hold 56-44, "
     "biggest Senate majority since 2009."),
    ("HEALTH", "DR CONGO", "#2F855A", icon_virus,
     "Ebola outbreak passes 11,000 cases, 5,400 dead",
     "WHO: cases doubled in three months. No approved vaccine for Bundibugyo strain; "
     "children over a quarter of cases."),
    ("SCIENCE", "DEEP SPACE", "#2C7A7B", icon_voyager,
     "Voyager 1 is now one light-day from Earth",
     "First human-made object so far out: 25.9 billion km away; radio signals now "
     "take 24 hours. Launched 1977."),
    ("DISASTER", "SOUTH PACIFIC", "#DD6B20", icon_cyclone,
     "Category 5 Cyclone Xavier hits Cook Islands",
     "Gusts up to 315 km/h; shelters open, Manihiki wharf damaged. No casualties "
     "reported so far."),
    ("MIDDLE EAST", "GAZA", "#B83280", icon_report,
     "Board of Peace report faults Israel and Hamas",
     "Neither side met its commitments to end the Gaza war, ceasefire at risk of "
     "collapse, says report seen by Reuters."),
]


def draw_header(cv):
    top = 182
    for y in range(top):
        cv.rect(0, y, W, y + 1, mix(NAVY, NAVY2, y / top))
    cv.rect(0, top, W, top + 5, GOLD)

    kicker = "WORLD NEWS IN ONE IMAGE"
    draw_text(cv, 32, 26, kicker, 17, GOLD, True, track=1.6)
    right = "8 STORIES \u00b7 5 CONTINENTS AND SPACE"
    draw_text(cv, W - 32 - text_width(right, 12, True, 1.0), 29, right, 12,
              mix(WHITE, NAVY2, 0.35), True, track=1.0)

    date = "WEDNESDAY, 18 NOVEMBER 2026"
    size = 50.0
    while text_width(date, size, True, 0.6) > W - 64:
        size -= 1
    draw_text(cv, 32, 66, date, size, WHITE, True, track=0.6)

    sub = "The day's top stories, from the APEC summit to the edge of the solar system"
    draw_text(cv, 32, 140, sub, 17, hexrgb("#BFD0F0"), False)


ICON, PAD, GAP_X = 104, 15, 14


def card_text_width(w):
    return w - PAD - ICON - GAP_X - 10


def draw_card(cv, x, y, w, h, n, story, hs, ds):
    cat, place, color, icon, head, detail = story
    accent = hexrgb(color)
    cv.rrect(x + 2, y + 3, x + w + 2, y + h + 3, 12, SHADOW)
    cv.rrect(x, y, x + w, y + h, 12, CARD)
    cv.rrect(x, y, x + 6, y + h, 3, accent)

    s = ICON
    ix, iy = x + PAD, y + (h - s) // 2
    icon(cv, ix, iy, s, accent)

    tx = ix + s + GAP_X
    tw = card_text_width(w)
    # number badge + category line
    cv.circle(tx + 10, y + 22, 10.5, accent)
    num = str(n)
    draw_text(cv, tx + 10 - text_width(num, 11, True) / 2, y + 16.5, num, 11, WHITE, True)
    tag = cat + "  \u00b7  " + place
    draw_text(cv, tx + 27, y + 16.5, tag, 11, accent, True, track=0.9)

    yy = y + 44
    for ln in wrap(head, hs, tw, True):
        draw_text(cv, tx, yy, ln, hs, INK, True)
        yy += hs * 1.48
    yy += 3
    for ln in wrap(detail, ds, tw, False):
        draw_text(cv, tx, yy, ln, ds, BODY, False)
        yy += ds * 1.55


def draw_footer(cv):
    y = 978
    cv.rect(0, y - 10, W, y - 9, mix(BG, INK, 0.18))
    src = ("Sources: Reuters, AP, AFP, TASS, UN News, WHO, NASA/JPL, RNZ, "
           "Fiji Meteorological Service")
    draw_text(cv, 32, y + 2, src, 11.5, MUTED, False)
    note = "Events of Wed 18 Nov 2026, or first reported that day. Drawn entirely in code."
    draw_text(cv, 32, y + 22, note, 11.5, MUTED, False)
    stamp = "18.11.2026"
    draw_text(cv, W - 32 - text_width(stamp, 20, True), y + 6, stamp, 20, NAVY2, True)


def layout():
    m, gap = 24, 14
    cw = (W - 2 * m - gap) // 2
    y0, y1 = 202, 960
    ch = (y1 - y0 - 3 * gap) // 4
    tw = card_text_width(cw)
    # one headline size and one body size for every card, the largest that fits all
    hs = min(fit_wrap(st[4], 21.0, tw, 2, bold=True, min_size=14)[1] for st in STORIES)
    ds = min(fit_wrap(st[5], 13.0, tw, 3, bold=False, min_size=10)[1] for st in STORIES)
    return [(m + (i % 2) * (cw + gap), y0 + (i // 2) * (ch + gap), cw, ch, i + 1, st, hs, ds)
            for i, st in enumerate(STORIES)]


def render():
    cv = Canvas(W, H, BG)
    draw_header(cv)
    for args in layout():
        draw_card(cv, *args)
    draw_footer(cv)
    return cv


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    data = render().png()
    with open(os.path.join(out_dir, "entry.png"), "wb") as f:
        f.write(data)


if __name__ == "__main__":
    main()
