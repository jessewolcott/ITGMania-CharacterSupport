# -*- coding: utf-8 -*-
"""Minimal reader for StepMania / ITGmania bitmap fonts.

Implements the parts of src/Font.cpp and src/RageBitmapTexture.cpp that matter
for inspecting and extending a font:

  * .redir chains, and theme-then-_fallback path resolution
  * [main] import=, plus the implicit "Common default" import on top-level fonts
  * Line / map / range directives, and the implicit ascii|cp1252|numbers
    defaults applied to 128 / 256 / 15 / 16-frame pages
  * the "(res WxH)" filename hint and "(doubleres)", which decide whether
    glyph widths are in image pixels or in smaller source units
"""
import os
import re
import glob

TEX = re.compile(
    r"^(?P<stem>.+?)(?: \[(?P<page>[^\]]+)\])? (?P<w>\d+)x(?P<h>\d+)"
    r"(?: \((?P<hint>[^)]*)\))?\.(?:png|jpg|jpeg|gif|bmp)$", re.I)
RES = re.compile(r"res (\d+)x(\d+)", re.I)

_ASCII = {i: i for i in range(128)}
_CP1252_HIGH = {
    0x80: 0x20AC, 0x82: 0x201A, 0x83: 0x0192, 0x84: 0x201E, 0x85: 0x2026,
    0x86: 0x2020, 0x87: 0x2021, 0x88: 0x02C6, 0x89: 0x2030, 0x8A: 0x0160,
    0x8B: 0x2039, 0x8C: 0x0152, 0x8E: 0x017D, 0x91: 0x2018, 0x92: 0x2019,
    0x93: 0x201C, 0x94: 0x201D, 0x95: 0x2022, 0x96: 0x2013, 0x97: 0x2014,
    0x98: 0x02DC, 0x99: 0x2122, 0x9A: 0x0161, 0x9B: 0x203A, 0x9C: 0x0153,
    0x9E: 0x017E, 0x9F: 0x0178}


def _cp1252():
    m = {}
    for f in range(256):
        c = _CP1252_HIGH.get(f, f if (f < 0x80 or f >= 0xA0) else None)
        if c is not None:
            m[f] = c
    return m


CHARMAPS = {
    "ascii": _ASCII,
    "cp1252": _cp1252(),
    "numbers": {i: ord("0") + i for i in range(10)},
}


def parse_ini(path):
    """-> {section: [(key, raw_value), ...]}, order and duplicates preserved."""
    sec, data = None, {}
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\r\n")
            s = line.strip()
            if s.startswith("[") and "]" in s:
                sec = s[1:s.index("]")]
                data.setdefault(sec, [])
            elif sec is not None and "=" in line and not s.startswith(("#", "//", ";")):
                k, v = line.split("=", 1)
                data[sec].append((k.strip(), v))
    return data


class Page(object):
    """One texture page of a font."""

    def glyph_box(self, frame):
        x = (frame % self.cols) * self.art_w
        y = (frame // self.cols) * self.art_h
        return (x, y, x + self.art_w, y + self.art_h)


class Font(object):
    """A resolved font file and its pages. Imports are listed, not merged."""

    def __init__(self, path, search_dirs):
        self.path = path
        self.dir = os.path.dirname(path)
        self.stem = os.path.basename(path)[:-4]
        self.search_dirs = search_dirs
        self.ini = parse_ini(path)
        self.common = {k.lower(): v for k, v in self.ini.get("common", [])}
        self.pages = {}
        self.chars = {}
        self._load_pages()

    def _num(self, page, key, default):
        sec = {k.lower(): v for k, v in self.ini.get(page, [])}
        v = sec.get(key, self.common.get(key))
        try:
            return int(str(v).strip())
        except (TypeError, ValueError):
            return default

    def _load_pages(self):
        from PIL import Image
        for fn in sorted(os.listdir(self.dir)):
            m = TEX.match(fn)
            if not m or m.group("stem") != self.stem:
                continue
            page = m.group("page") or "main"
            if page.endswith("-stroke"):
                continue
            p = Page()
            p.name = page
            p.png = os.path.join(self.dir, fn)
            p.cols, p.rows = int(m.group("w")), int(m.group("h"))
            with Image.open(p.png) as im:
                iw, ih = im.size
            p.art_w, p.art_h = iw / p.cols, ih / p.rows
            hint = m.group("hint") or ""
            mr = RES.search(hint)
            sw, sh = (int(mr.group(1)), int(mr.group(2))) if mr else (iw, ih)
            if "doubleres" in hint.lower():
                sw, sh = sw // 2, sh // 2
            p.src_w, p.src_h = sw / p.cols, sh / p.rows
            p.scale = p.art_w / p.src_w
            p.line_spacing = self._num(page, "linespacing", int(round(p.src_h)))
            p.baseline = self._num(page, "baseline", -1)
            p.top = self._num(page, "top", -1)
            if p.baseline < 0:
                p.baseline = int(p.src_h / 2.0 + p.line_spacing / 2)
            if p.top < 0:
                p.top = int(p.src_h / 2.0 - p.line_spacing / 2)
            p.extra_l = self._num(page, "drawextrapixelsleft", 0)
            p.extra_r = self._num(page, "drawextrapixelsright", 0)
            p.adv_extra = self._num(page, "advanceextrapixels", 0)
            p.widths, p.chars = self._page_chars(page, p)
            self.pages[page] = p
            for ch, fr in p.chars.items():
                self.chars.setdefault(ch, (page, fr))

    def _page_chars(self, page, p):
        widths, chars = {}, {}
        for k, v in self.ini.get(page, []):
            name = k.strip()
            low = name.lower()
            if name.isdigit():
                try:
                    widths[int(name)] = int(v.strip())
                except ValueError:
                    pass
            elif low.startswith("line "):
                row_s = name.split(None, 1)[1].strip()
                if not row_s.isdigit():
                    continue
                row = int(row_s)
                for i, ch in enumerate(v):
                    chars[ch] = row * p.cols + i
            elif low.startswith("map "):
                cp = name.split(None, 1)[1].strip()
                try:
                    frame = int(v.strip())
                except ValueError:
                    continue
                if cp.upper().startswith("U+"):
                    try:
                        chars[chr(int(cp[2:], 16))] = frame
                    except ValueError:
                        pass
                elif len(cp) == 1:
                    chars[cp] = frame
            elif low.startswith("range "):
                m = re.match(
                    r"range\s+([A-Za-z0-9\-]+)(?:\s*#([0-9A-Fa-f]+)-([0-9A-Fa-f]+))?$",
                    name, re.I)
                if not m:
                    continue
                try:
                    first = int(v.strip())
                except ValueError:
                    continue
                cs, lo, hi = m.group(1).lower(), m.group(2), m.group(3)
                if cs == "unicode":
                    if lo is None:
                        continue
                    for n, c in enumerate(range(int(lo, 16), int(hi, 16) + 1)):
                        chars[chr(c)] = first + n
                elif cs in CHARMAPS:
                    for f, c in CHARMAPS[cs].items():
                        if lo is None or int(lo, 16) <= f <= int(hi, 16):
                            chars[chr(c)] = first + f
        if not chars and page != "common":
            n = p.cols * p.rows
            cm = {128: "ascii", 256: "cp1252", 15: "numbers", 16: "numbers"}.get(n)
            if cm:
                chars = {chr(c): f for f, c in CHARMAPS[cm].items()}
        if " " in chars:
            chars.setdefault(" ", chars[" "])
        return widths, chars

    def imports(self, top_level=True):
        out = ["Common default"] if top_level else []
        for k, v in self.ini.get("main", []):
            if k.strip().lower() == "import":
                out += [s.strip() for s in v.split(",") if s.strip()]
        return out

    def width(self, ch):
        page, fr = self.chars[ch]
        p = self.pages[page]
        return p.widths.get(fr, self._num(page, "defaultwidth", int(round(p.src_w))))

    def cell(self, ch):
        """Full art-resolution RGBA cell image for `ch`."""
        from PIL import Image
        page, fr = self.chars[ch]
        p = self.pages[page]
        with Image.open(p.png) as im:
            box = p.glyph_box(fr)
            return im.convert("RGBA").crop(
                (int(box[0]), int(box[1]), int(box[2]), int(box[3])))


def resolve(name, search_dirs, _depth=0):
    """Resolve a font name through .redir chains, theme dir before _fallback."""
    if _depth > 10:
        return None
    for base in search_dirs:
        p = os.path.join(base, name)
        for cand in (p + ".redir", p + ".ini"):
            if os.path.isfile(cand):
                if cand.endswith(".redir"):
                    tgt = open(cand, encoding="utf-8-sig").read().strip()
                    return resolve(tgt, search_dirs, _depth + 1)
                return cand
        hits = sorted(glob.glob(glob.escape(p) + " *.ini"))
        if hits:
            return hits[0]
    return None


def load(name, search_dirs):
    p = resolve(name, search_dirs)
    return Font(p, search_dirs) if p else None


def coverage(name, search_dirs, _seen=None, _top=True):
    """char -> (ini_path, page_name), following imports the way Font::Load does.

    The ini path is returned rather than the font's name because a font can
    live in a subdirectory (Simply Love keeps Miso in Fonts/Miso/), so its
    stem alone is not resolvable.
    """
    _seen = _seen if _seen is not None else set()
    path = resolve(name, search_dirs)
    if path is None or path in _seen:
        return {}
    _seen.add(path)
    f = Font(path, search_dirs)
    cov = {}
    # Font::Load merges imports in order via MergeFont, which assigns into
    # m_iCharToGlyph - so a LATER import overrides an earlier one, and the
    # font's own pages override every import.
    for imp in f.imports(_top):
        cov.update(coverage(imp, search_dirs, _seen, False))
    for page, p in f.pages.items():
        for ch in p.chars:
            cov[ch] = (path, page)
    return cov


def label(src):
    """Human-readable 'font [page]' for a coverage value."""
    path, page = src
    return "%s [%s]" % (os.path.basename(path)[:-4], page)
