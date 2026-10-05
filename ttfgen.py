# -*- coding: utf-8 -*-
"""Generate Thai and Korean font pages from a TrueType font, sized and
baselined to match a theme's own body font.

Unlike Vietnamese, these scripts cannot be composited out of Latin letterforms,
so they need a real source font. Both OFL fonts used by default ship with
Windows (Noto Sans Thai, NanumGothic) and are redistributable.

Thai needs the engine's zero-advance overlay trick: StepMania does no text
shaping, so a combining mark is given width 0 plus a large DrawExtraPixels,
which makes the engine draw its whole cell centred on the pen without
advancing. The mark art therefore has to sit left of its cell centre so it
lands over the preceding consonant. The shipped _Thai 16px font does exactly
this (its [Sara2] page is all zero widths); we measure the offset instead of
guessing it.
"""
import math
import unicodedata

from PIL import Image, ImageChops, ImageDraw, ImageFont

import fontspec

THAI_BLOCK = [chr(c) for c in range(0x0E01, 0x0E60)]
HANGUL = [chr(c) for c in range(0xAC00, 0xD7A4)]


# ------------------------------------------------------------------ helpers
def body_metrics(body):
    """Cap height / baseline / line spacing of a theme font, in SOURCE units."""
    page = body.pages["main"]
    ref = "H" if "H" in body.chars else "O"
    bb = body.cell(ref).split()[-1].getbbox()
    cap_art = bb[3] - bb[1]
    xref = "x" if "x" in body.chars else "o"
    xbb = body.cell(xref).split()[-1].getbbox()
    return {
        "cap": cap_art / page.scale,
        "xheight": (xbb[3] - xbb[1]) / page.scale,
        "baseline": page.baseline,
        "top": page.top,
        "line_spacing": page.line_spacing,
        "extra_l": page.extra_l,
        "extra_r": page.extra_r,
    }


def _ink(img):
    return img.split()[-1].getbbox()


def _draw(font, text, w, h, x, baseline):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((x, baseline), text, font=font,
                            fill=(255, 255, 255, 255), anchor="ls")
    return im


def _fit_size(ttf, ref, target_h):
    """Point size at which `ref` renders target_h pixels tall."""
    lo, hi, best = 4, 600, 12
    while lo <= hi:
        mid = (lo + hi) // 2
        f = ImageFont.truetype(ttf, mid)
        im = _draw(f, ref, mid * 4, mid * 4, mid, mid * 2)
        bb = _ink(im)
        h = (bb[3] - bb[1]) if bb else 0
        if h < target_h:
            lo = mid + 1
        else:
            hi = mid - 1
            best = mid
    return max(4, best)


def _pack(n, cell_w, cell_h, max_tex):
    """Grid that keeps each page inside the texture cap."""
    cols = max(1, max_tex // cell_w)
    rows_per_page = max(1, max_tex // cell_h)
    per_page = cols * rows_per_page
    return cols, rows_per_page, int(math.ceil(n / float(per_page)))


# ------------------------------------------------------------------ Korean
def build_cjk(body, ttf, chars, ref="한", notes=None, oversample=None,
              max_tex=2048, max_pages=2, source_label="", log=None):
    """Monospaced ideographic page (Hangul syllables, Han, kana).

    oversample=None picks the sharpest texture scale that still fits the whole
    set inside `max_pages` textures of `max_tex` square.
    """
    if oversample is None:
        for o in (3, 2, 1):
            if _cjk_pages(body, ttf, chars, o, max_tex, ref) <= max_pages:
                oversample = o
                break
        oversample = oversample or 1
    bm = body_metrics(body)
    target = bm["cap"] * 1.12 * oversample     # CJK reads small at cap height
    size = _fit_size(ttf, ref, target)
    font = ImageFont.truetype(ttf, size)

    # Drop anything this font cannot actually draw, so a source font with
    # partial coverage degrades to "fewer glyphs" rather than a page of blanks.
    present, absent = [], []
    for ch in chars:
        try:
            # whitespace legitimately has no ink - keep it, or the ideographic
            # space would fall through to the blank "missing" glyph
            ok = font.getmask(ch).getbbox() or unicodedata.category(ch) == "Zs"
        except Exception:
            ok = False
        (present if ok else absent).append(ch)
    chars = present

    # measure the extremes over a sample so the cell fits every glyph
    sample = chars[::max(1, len(chars) // 400)]
    pad = size * 2
    top, bot, wide = 10 ** 6, -10 ** 6, 0
    for ch in sample:
        bb = _ink(_draw(font, ch, pad * 3, pad * 3, pad, pad * 2))
        if not bb:
            continue
        top = min(top, bb[1] - pad * 2)
        bot = max(bot, bb[3] - pad * 2)
        wide = max(wide, bb[2] - bb[0])
    adv_art = int(math.ceil(max(wide, font.getlength(ref))))

    adv_src = max(1, int(math.ceil(adv_art / float(oversample))))
    cell_w = adv_src * oversample
    margin = max(1, oversample)
    asc, desc = -top + margin, bot + margin
    cell_h_src = int(math.ceil((asc + desc) / float(oversample)))
    if cell_h_src % 2:
        cell_h_src += 1
    cell_h = cell_h_src * oversample
    baseline_art = asc
    baseline_src = int(round(baseline_art / float(oversample)))

    cols, rows_per_page, npages = _pack(len(chars), cell_w, cell_h, max_tex)
    spec = fontspec.new_spec(
        (cell_w // oversample, cell_h_src),
        {"Baseline": baseline_src,
         "Top": baseline_src - (bm["baseline"] - bm["top"]),
         "LineSpacing": bm["line_spacing"],
         "DefaultWidth": adv_src,
         "DrawExtraPixelsLeft": bm["extra_l"],
         "DrawExtraPixelsRight": bm["extra_r"]},
        source_label or ttf)
    spec["missing"] = [(c, "not in source font") for c in absent]
    spec["notes"] = list(notes or []) + [
        "Rendered at the body font's cap height and monospaced at %d source px."
        % adv_src]

    for pi in range(npages):
        chunk = chars[pi * cols * rows_per_page:(pi + 1) * cols * rows_per_page]
        if not chunk:
            break
        rows = int(math.ceil(len(chunk) / float(cols)))
        im = Image.new("RGBA", (cell_w * cols, cell_h * rows), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        for i, ch in enumerate(chunk):
            x = (i % cols) * cell_w + cell_w / 2.0
            y = (i // cols) * cell_h + baseline_art
            d.text((x, y), ch, font=font, fill=(255, 255, 255, 255), anchor="ms")
        name = "main" if pi == 0 else "p%d" % (pi + 1)
        fontspec.add_page(spec, name, im, cols, rows, chunk, {})
        if log:
            log("      page %-4s %5d glyphs  %dx%d px" % (name, len(chunk), im.width, im.height))
    return spec


def _cjk_pages(body, ttf, chars, oversample, max_tex, ref):
    """Page count for a trial oversample, without rendering anything."""
    bm = body_metrics(body)
    size = _fit_size(ttf, ref, bm["cap"] * 1.12 * oversample)
    f = ImageFont.truetype(ttf, size)
    adv = int(math.ceil(f.getlength(ref)))
    cell_w = max(1, int(math.ceil(adv / float(oversample)))) * oversample
    cell_h = int(math.ceil(size * 1.45))
    cols = max(1, max_tex // cell_w)
    rows = max(1, max_tex // cell_h)
    return int(math.ceil(len(chars) / float(cols * rows)))


def build_korean(body, ttf, chars=None, **kw):
    return build_cjk(body, ttf, chars or HANGUL, ref="한",
                     notes=["Full precomposed Hangul syllable block.",
                            "The shipped _korean 24px [jamo N] pages are not jamo -",
                            "they are ~246 hand-picked syllables, so most Hangul was missing."],
                     **kw)


def build_chinese(body, ttf, chars=None, **kw):
    return build_cjk(body, ttf, chars or cjk_set(), ref="國",
                     notes=["Han (GB2312 + Big5), kana and CJK punctuation.",
                            "Chinese previously had no font of its own: _chinese 24px is",
                            "126 hand-picked UI words, so Chinese text was being rendered",
                            "by the Japanese JIS kanji pages. That covers most traditional",
                            "forms but almost no PRC-simplified ones.",
                            "Kana is included so Japanese titles do not end up half in",
                            "this face and half in the larger shipped JIS pages."],
                     **kw)


def _encodable(codec, lo, hi):
    out = []
    for c in range(lo, hi):
        ch = chr(c)
        try:
            ch.encode(codec)
            out.append(ch)
        except Exception:
            pass
    return set(out)


_CJK_SET = None


def cjk_set():
    """Han from GB2312 (simplified) and Big5 (traditional), plus kana and the
    CJK punctuation block."""
    global _CJK_SET
    if _CJK_SET is None:
        han = _encodable("gb2312", 0x4E00, 0xA000) | _encodable("big5", 0x4E00, 0xA000)
        kana = {chr(c) for c in range(0x3040, 0x3100)}
        punc = {chr(c) for c in range(0x3000, 0x3040)}
        _CJK_SET = sorted(han | kana | punc)
    return _CJK_SET


# ------------------------------------------------------------------ Thai
def build_thai(body, ttf, oversample=2, max_tex=2048, source_label="", log=None):
    bm = body_metrics(body)
    # Thai is sized off the Latin x-height, not the cap height: KO KAI is an
    # x-height-class letterform, so matching it to caps makes Thai text sit
    # noticeably larger than the Latin around it.
    target = bm["xheight"] * 1.15 * oversample
    size = _fit_size(ttf, "ก", target)          # KO KAI
    font = ImageFont.truetype(ttf, size)
    pad = size * 3

    spacing, marks = [], []
    for ch in THAI_BLOCK:
        try:
            if not _ink(_draw(font, ch, pad * 3, pad * 3, pad, pad * 2)) and \
               unicodedata.category(ch) != "Mn":
                continue
        except Exception:
            continue
        (marks if unicodedata.category(ch) == "Mn" else spacing).append(ch)

    # monospace advance, as the shipped Thai font does - it makes the overlay
    # offset for combining marks a single known quantity
    # Median consonant advance. Using max() would monospace the whole script
    # to the widest symbol in the block (currency, ellipsis) and space Thai
    # text out absurdly.
    cons = sorted(font.getlength(c) for c in spacing
                  if unicodedata.category(c) == "Lo")
    adv_art = int(math.ceil(cons[len(cons) // 2] if cons else
                            max(font.getlength(c) for c in spacing)))
    adv_src = max(1, int(math.ceil(adv_art / float(oversample))))

    base = "ก"
    base_im = _draw(font, base, pad * 3, pad * 3, pad, pad * 2)
    base_bb = _ink(base_im)
    base_cx = (base_bb[0] + base_bb[2]) / 2.0

    # isolate each mark by diffing "base+mark" against "base"
    mark_art = {}
    top_most, bot_most = base_bb[1], base_bb[3]
    for m in marks:
        comp = _draw(font, base + m, pad * 3, pad * 3, pad, pad * 2)
        diff = ImageChops.difference(comp.split()[-1], base_im.split()[-1])
        diff = diff.point(lambda v: 255 if v > 40 else 0)
        bb = diff.getbbox()
        if not bb:
            continue
        tile = comp.crop(bb)
        tile.putalpha(diff.crop(bb))
        # dx: where the mark sits relative to the base glyph's ink centre
        # above: how far the mark's top sits above the baseline (negative for
        #        the below-base vowels, which is exactly what we want)
        mark_art[m] = (tile,
                       (bb[0] + bb[2]) / 2.0 - base_cx,
                       pad * 2 - bb[1])
        top_most = min(top_most, bb[1])
        bot_most = max(bot_most, bb[3])
    for ch in spacing:
        bb = _ink(_draw(font, ch, pad * 3, pad * 3, pad, pad * 2))
        if bb:
            top_most, bot_most = min(top_most, bb[1]), max(bot_most, bb[3])

    margin = max(1, oversample)
    asc = (pad * 2 - top_most) + margin
    desc = (bot_most - pad * 2) + margin
    cell_h_src = int(math.ceil((asc + desc) / float(oversample)))
    if cell_h_src % 2:
        cell_h_src += 1
    cell_h = cell_h_src * oversample
    baseline_art = asc
    baseline_src = int(round(baseline_art / float(oversample)))

    # cell wide enough that a zero-width mark, drawn centred on the pen, still
    # reaches back over the preceding consonant
    cell_w_src = adv_src * 3
    if cell_w_src % 2:
        cell_w_src += 1
    cell_w = cell_w_src * oversample

    order = spacing + [m for m in marks if m in mark_art]
    cols = min(16, max(1, max_tex // cell_w))
    rows = int(math.ceil(len(order) / float(cols)))
    im = Image.new("RGBA", (cell_w * cols, cell_h * rows), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    widths = {}

    for i, ch in enumerate(order):
        ox, oy = (i % cols) * cell_w, (i // cols) * cell_h
        if ch in mark_art:
            tile, delta, above = mark_art[ch]
            # a zero-width glyph is drawn centred on the pen, which sits just
            # past the preceding consonant - so shift the mark back by half an
            # advance to centre it over that consonant
            cx = cell_w / 2.0 - (adv_src * oversample) / 2.0 + delta
            x = int(round(ox + cx - tile.width / 2.0))
            y = int(round(oy + baseline_art - above))
            im.alpha_composite(tile, (max(ox, x), max(oy, y)))
            widths[i] = 0
        else:
            d.text((ox + cell_w / 2.0, oy + baseline_art), ch, font=font,
                   fill=(255, 255, 255, 255), anchor="ms")
            widths[i] = adv_src

    spec = fontspec.new_spec(
        (cell_w_src, cell_h_src),
        {"Baseline": baseline_src,
         "Top": baseline_src - (bm["baseline"] - bm["top"]),
         "LineSpacing": bm["line_spacing"],
         "DefaultWidth": adv_src,
         "DrawExtraPixelsLeft": cell_w_src,
         "DrawExtraPixelsRight": cell_w_src},
        source_label or ttf)
    spec["notes"] = [
        "Spacing glyphs are monospaced at %d source px." % adv_src,
        "Combining marks have width 0 and rely on DrawExtraPixels to be drawn",
        "over the preceding consonant, as the shipped _Thai 16px page does."]
    fontspec.add_page(spec, "main", im, cols, rows, order, widths)
    if log:
        log("      %d spacing + %d combining, cell %dx%d src, %dx%d px"
            % (len(spacing), len(mark_art), cell_w_src, cell_h_src, im.width, im.height))
    return spec
