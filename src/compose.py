# -*- coding: utf-8 -*-
"""Build a Vietnamese font page composited from any bitmap font's own glyphs.

Everything is derived from the source font - cell geometry, baseline, stroke
weight, x-height, mark shapes - so the same code produces a matching page for
Miso Light, Open Sans, Roboto or anything else shaped like a StepMania font.

Chars produced: U+1EA0..U+1EF9 plus the horn letters O-horn / U-horn.
"""
import unicodedata
from PIL import Image

TARGETS = [chr(c) for c in range(0x1EA0, 0x1EFA)] + ["Ơ", "ơ", "Ư", "ư"]
TARGETS = [c for c in TARGETS if unicodedata.category(c) in ("Lu", "Ll")]

CIRCUMFLEX, BREVE, HORN_CP = 0x0302, 0x0306, 0x031B
ACUTE, GRAVE, TILDE, HOOK, DOT_BELOW = 0x0301, 0x0300, 0x0303, 0x0309, 0x0323

PLAIN_BASES = set("aeiouyAEIOUY")


def _alpha(img):
    return img.split()[-1]


def _bbox(img):
    return _alpha(img).getbbox()


def _tight(img):
    bb = _bbox(img)
    return img.crop(bb) if bb else img


def _row_widths(img):
    """Per-row ink extent, as (first, last, width) or None for blank rows."""
    a = _alpha(img)
    w, h = a.size
    px = a.load()
    out = []
    for y in range(h):
        lo, hi = None, None
        for x in range(w):
            if px[x, y] > 24:
                if lo is None:
                    lo = x
                hi = x
        out.append(None if lo is None else (lo, hi, hi - lo + 1))
    return out


class Builder(object):
    def __init__(self, font, log=print):
        self.f = font
        self.log = log
        self.page = font.pages["main"]
        self.scale = self.page.scale
        self.art_w = int(round(self.page.art_w))
        self.art_h = int(round(self.page.art_h))
        self.baseline = self.page.baseline            # source units
        self.baseline_art = self.baseline * self.scale
        self.missing = []
        self._measure()
        self._marks()

    # ---------------------------------------------------------------- metrics
    def _measure(self):
        f = self.f
        xb = _bbox(f.cell("x")) if "x" in f.chars else _bbox(f.cell("o"))
        cb = _bbox(f.cell("H")) if "H" in f.chars else _bbox(f.cell("O"))
        self.x_top, self.x_bot = xb[1], xb[3]
        self.cap_top = cb[1]
        self.x_height = self.x_bot - self.x_top
        # stroke weight: narrowest row of a plain vertical stem
        stem = None
        for ch in ("l", "I", "i", "t"):
            if ch in f.chars:
                rows = [r for r in _row_widths(f.cell(ch)) if r]
                if rows:
                    stem = min(r[2] for r in rows)
                    break
        self.stroke = stem or max(2, int(self.x_height * 0.12))
        self.gap_above = max(1, int(round(self.x_height * 0.08)))
        self.gap_stack = max(1, int(round(self.x_height * 0.04)))
        self.gap_below = max(1, int(round(self.x_height * 0.18)))

    # ---------------------------------------------------------------- marks
    def _mark_from(self, composed, base):
        """Isolate the mark of a precomposed glyph: everything above the
        base letter's own ink top."""
        f = self.f
        if composed not in f.chars or base not in f.chars:
            return None
        cut = _bbox(f.cell(base))[1] - 1
        if cut <= 0:
            return None
        m = f.cell(composed).crop((0, 0, self.art_w, cut))
        return _tight(m) if _bbox(m) else None

    def _hook(self):
        """dau hoi: the bowl of '?', with stem and dot removed."""
        f = self.f
        if "?" not in f.chars:
            return None
        q = f.cell("?")
        rows = _row_widths(q)
        bands, cur = [], None
        for y, r in enumerate(rows):
            if r and cur is None:
                cur = [y, y]
            elif r:
                cur[1] = y
            elif cur:
                bands.append(cur); cur = None
        if cur:
            bands.append(cur)
        if not bands:
            return None
        # bands[0] is the bowl plus the stem below it; the dot is a later band.
        # dau hoi is the arc AND the tail that descends from it - cutting at the
        # point where the row extent narrows would keep only the arc, which
        # reads as a breve. Take a fixed share of the band instead.
        top, bot = bands[0]
        cut = top + max(2, int(round((bot - top) * 0.58)))
        bowl = _tight(q.crop((0, top, self.art_w, min(cut, bot + 1))))
        target_h = int(round(self.x_height * 0.52))
        if bowl.height < 2 or target_h < 2:
            return None
        w = max(1, int(round(bowl.width * target_h / bowl.height)))
        return bowl.resize((w, target_h), Image.LANCZOS)

    def _horn(self):
        f = self.f
        src = next((c for c in ("’", "'", ",") if c in f.chars), None)
        if src is None:
            return None
        a = _tight(f.cell(src))
        target_h = int(round(self.x_height * 0.42))
        w = max(1, int(round(a.width * target_h / a.height)))
        a = a.resize((w, target_h), Image.LANCZOS)
        return a.transpose(Image.FLIP_LEFT_RIGHT)

    def _marks(self):
        self.MARK = {
            ACUTE: self._mark_from("á", "a"),
            GRAVE: self._mark_from("à", "a"),
            TILDE: self._mark_from("ã", "a"),
            HOOK:  self._hook(),
        }
        self.DOT = _tight(self.f.cell(".")) if "." in self.f.chars else None
        self.HORN = self._horn()

    # ---------------------------------------------------------------- compose
    def _canvas(self, pad_top, pad_bot):
        return Image.new("RGBA", (self.art_w, self.art_h + pad_top + pad_bot), (0, 0, 0, 0))

    def _compose(self, ch, pad_top, pad_bot):
        """Returns an image on a padded canvas, or raises KeyError."""
        d = unicodedata.normalize("NFD", ch)
        base = d[0]
        marks = [ord(c) for c in d[1:]]
        horn = HORN_CP in marks
        marks = [m for m in marks if m != HORN_CP]

        stack = []
        for m in marks:
            if m == CIRCUMFLEX:
                base = unicodedata.normalize("NFC", base + "̂")
            elif m == BREVE:
                base = unicodedata.normalize("NFC", base + "̆")
            else:
                stack.append(m)
        if base not in self.f.chars:
            raise KeyError("no glyph for base %r" % base)

        im = self._canvas(pad_top, pad_bot)
        im.alpha_composite(self.f.cell(base), (0, pad_top))
        adv = self.f.width(base)

        base_bb = _bbox(im)
        if horn:
            if self.HORN is None:
                raise KeyError("no horn source")
            x = min(base_bb[2] - max(1, self.stroke // 2), self.art_w - self.HORN.width)
            y = max(0, base_bb[1] - self.HORN.height // 3)
            im.alpha_composite(self.HORN, (int(x), int(y)))

        stacked = base not in PLAIN_BASES
        for m in stack:
            if m == DOT_BELOW:
                if self.DOT is None:
                    raise KeyError("no dot source")
                cx = (base_bb[0] + base_bb[2]) // 2
                y = int(pad_top + self.baseline_art + self.gap_below)
                y = min(y, im.height - self.DOT.height)
                im.alpha_composite(self.DOT, (int(cx - self.DOT.width // 2), y))
            else:
                mk = self.MARK.get(m)
                if mk is None:
                    raise KeyError("no source for mark U+%04X" % m)
                bb = _bbox(im)
                cx = (base_bb[0] + base_bb[2]) // 2
                gap = self.gap_stack if stacked else self.gap_above
                y = bb[1] - gap - mk.height
                im.alpha_composite(mk, (int(max(0, cx - mk.width // 2)), int(max(0, y))))
                stacked = True
        return im, adv

    # ---------------------------------------------------------------- widths
    def _fit_width(self, im, adv):
        """Grow the advance until the ink fits Font.cpp's centred crop window."""
        eL, eR = self.page.extra_l + 1, self.page.extra_r + 1
        if eL % 2:
            eL += 1
        bb = _bbox(im)
        if bb is None:
            return adv
        cx = self.art_w / 2.0
        cap = int(self.page.src_w)
        while adv < cap:
            half = adv * self.scale / 2.0
            if bb[0] >= cx - half - eL * self.scale - 0.5 and \
               bb[2] <= cx + half + eR * self.scale + 0.5:
                break
            adv += 1
        return adv

    # ---------------------------------------------------------------- build
    def build(self, cols=10):
        """-> (page_image, {frame: advance}, chars_in_order, baseline, top, res)"""
        probe_pad = self.art_h
        built, self.missing = [], []
        for ch in TARGETS:
            try:
                im, adv = self._compose(ch, probe_pad, probe_pad)
            except KeyError as e:
                self.missing.append((ch, str(e)))
                continue
            built.append((ch, im, adv))
        if not built:
            raise RuntimeError("could not build any glyph from this font")

        # how much extra room did the marks actually need?
        over_top = min(_bbox(im)[1] for _, im, _ in built)
        over_bot = max(_bbox(im)[3] for _, im, _ in built)
        margin = max(1, int(round(self.x_height * 0.06)))
        need_top = max(0, probe_pad - over_top + margin)
        need_bot = max(0, over_bot - (probe_pad + self.art_h) + margin)
        # express padding in whole source units so Baseline stays an integer
        pad_top_src = int(-(-need_top // self.scale))
        pad_bot_src = int(-(-need_bot // self.scale))
        if (int(round(self.page.src_h)) + pad_top_src + pad_bot_src) % 2:
            pad_bot_src += 1
        pad_top = int(round(pad_top_src * self.scale))
        pad_bot = int(round(pad_bot_src * self.scale))

        cell_h = self.art_h + pad_top + pad_bot
        rows = -(-len(built) // cols)
        page = Image.new("RGBA", (self.art_w * cols, cell_h * rows), (0, 0, 0, 0))
        widths, order = {}, []
        for i, (ch, _, _) in enumerate(built):
            im, adv = self._compose(ch, pad_top, pad_bot)
            adv = self._fit_width(im, adv)
            page.alpha_composite(im, ((i % cols) * self.art_w, (i // cols) * cell_h))
            widths[i] = adv
            order.append(ch)

        src_w_total = int(round(self.page.src_w)) * cols
        src_h_total = (int(round(self.page.src_h)) + pad_top_src + pad_bot_src) * rows
        return {
            "image": page, "widths": widths, "chars": order,
            "cols": cols, "rows": rows,
            "baseline": self.baseline + pad_top_src,
            "top": self.page.top + pad_top_src,
            "line_spacing": self.page.line_spacing,
            "extra_l": self.page.extra_l, "extra_r": self.page.extra_r,
            "res": (src_w_total, src_h_total),
        }


    # ------------------------------------------------------------ spec
    def build_spec(self, cols=10):
        """The same page, in the shared fontspec format."""
        import os
        import fontspec
        s = self.build(cols)
        src_w = s["res"][0] // s["cols"]
        src_h = s["res"][1] // s["rows"]
        spec = fontspec.new_spec(
            (src_w, src_h),
            {"Baseline": s["baseline"], "Top": s["top"],
             "LineSpacing": s["line_spacing"],
             "DrawExtraPixelsLeft": s["extra_l"],
             "DrawExtraPixelsRight": s["extra_r"]},
            os.path.basename(self.f.path))
        spec["notes"] = [
            "Composited from that font's own letterforms and diacritics.",
            "Cells are taller than the source page so stacked tone marks have",
            "headroom above capitals; Baseline and Top are shifted by the same",
            "amount, so Baseline-Top (the line height) is unchanged."]
        fontspec.add_page(spec, "main", s["image"], s["cols"], s["rows"],
                          s["chars"], s["widths"])
        return spec


def ini_text(spec, source_name):
    L = [
        "# Vietnamese (Latin Extended Additional + o/u-horn).",
        "# Generated by fontpatch.py - composited from the glyphs of:",
        "#   %s" % source_name,
        "# so the letterforms, stroke weight and metrics match that font.",
        "#",
        "# The cell is taller than the source font's so stacked tone marks have",
        "# headroom above capitals. Baseline and Top are both shifted by that",
        "# same amount, which keeps Baseline-Top (the line height) unchanged.",
        "",
        "[common]",
        "Baseline=%d" % spec["baseline"],
        "Top=%d" % spec["top"],
        "LineSpacing=%d" % spec["line_spacing"],
        "DrawExtraPixelsLeft=%d" % spec["extra_l"],
        "DrawExtraPixelsRight=%d" % spec["extra_r"],
        "",
        "[main]",
    ]
    cols, chars = spec["cols"], spec["chars"]
    for r in range(spec["rows"]):
        chunk = "".join(chars[r * cols:(r + 1) * cols])
        if chunk:
            L.append("Line %-2d=%s" % (r, chunk))
    L.append("")
    L += ["%d=%d" % (k, v) for k, v in sorted(spec["widths"].items())]
    return "\r\n".join(L) + "\r\n"
