# 03 — Glyph generation algorithms

Two generators, both emitting the shared spec defined in `fontspec.py`:

| module | strategy | used for |
|---|---|---|
| `compose.py` | composite from the target font's **own** glyphs | Vietnamese |
| `ttfgen.py` | render from a system TrueType font | Thai, Korean, Chinese |

Vietnamese can be composited because every piece it needs — base vowels and
the acute/grave/tilde/circumflex/breve marks — already exists in any Latin-1 +
Latin-2 font. Thai and CJK have no such source, so they must come from a real
font and the best that can be done is to match the theme's metrics.

---

## Shared: measuring the target font

`ttfgen.body_metrics()` measures, in **source units**:

```python
cap      = ink height of 'H' (or 'O')   / page.scale
xheight  = ink height of 'x' (or 'o')   / page.scale
baseline, top, line_spacing, extra_l, extra_r   # straight from the page
```

`page.scale = art_cell_width / source_frame_width` — the oversampling factor
of the existing art (5.33× for Simply Love's Miso Light, 1× for most
`_fallback` fonts). Everything is converted through it so the same code works
regardless of how oversampled the theme's art is.

---

## Vietnamese — `compose.py`

### Target set

`U+1EA0–U+1EF9` filtered to letters, plus the four horn letters `U+01A0`,
`U+01A1`, `U+01AF`, `U+01B0` — 94 glyphs. The circumflex/breve bases
(`Ă ă Â â Ê ê Ô ô`) and `Đ đ` already exist in Latin-1/Latin-2 and are not
regenerated.

### Decomposition

Each target is NFD-decomposed. Circumflex and breve are **recomposed into the
base** (so `ấ` starts from the existing `â` glyph rather than stacking a
circumflex), leaving at most one tone mark plus an optional horn:

```python
d = unicodedata.normalize("NFD", ch)      # 'ấ' -> 'a' + U+0302 + U+0301
base = 'a'
for m in marks:
    if m == CIRCUMFLEX: base = NFC(base + '̂')   # -> 'â'
    elif m == BREVE:    base = NFC(base + '̆')   # -> 'ă'
    else: stack.append(m)
```

### Extracting the marks

A mark is isolated from a precomposed glyph by cropping everything **above the
base letter's own ink top**:

```python
cut = bbox(font.cell('a'))[1] - 1
mark = font.cell('á').crop((0, 0, cell_w, cut))
```

This is exact and font-independent — far better than `ImageChops.subtract`,
which leaves antialiasing residue along the shared edges (tried first; it
produced marks whose bounding boxes ran all the way to the baseline).

Three marks have no precomposed source and are derived instead:

| mark | derivation |
|---|---|
| **dot below** | the font's `.`, repositioned below the baseline |
| **horn** | the font's `’`, scaled to ~0.42 × x-height and mirrored |
| **hook above** (`dấu hỏi`) | the bowl of the font's `?` |

The hook is the subtle one. `?` is split into contiguous ink row-bands; the
first band is bowl + stem (the dot is a later band and is discarded). The hook
is then a **fixed 58 % of that band's height**.

An earlier version cut where the row extent narrowed, on the theory that this
marked the end of the bowl. It does not: below the arc, only the descending
right stroke has ink, so the measured extent collapses immediately and the cut
lands right after the arc. The result rendered as a breve, not a hook. A
`dấu hỏi` needs the arc *and* its descending tail.

### Placement

All gaps are expressed as fractions of the measured x-height, so they scale
across fonts:

```python
gap_above = 0.08 * x_height     # ink -> first mark
gap_stack = 0.04 * x_height     # mark -> mark
gap_below = 0.18 * x_height     # baseline -> dot below
```

A mark is centred on the **base letter's** ink, not on whatever is currently
topmost — centring on an existing narrow circumflex would drift the tone mark
off-centre. A mark stacks (uses `gap_stack`) when the base already carries one,
i.e. when it is not a plain `a e i o u y / A E I O U Y`.

### Cell sizing

Rather than guessing headroom, every glyph is composed once onto a generously
padded canvas, the extremes are measured, and the real padding is derived:

```python
over_top = min(bbox(g)[1] for g in built)
need_top = probe_pad - over_top + margin
pad_top_src = ceil(need_top / scale)        # whole source units
```

Rounding to whole source units keeps `Baseline` an integer. `Baseline` and
`Top` both increase by `pad_top_src`, so `Baseline - Top` — the line height —
is unchanged. See [01](01-engine-internals.md#vertical-metrics).

### Width fitting

Because the engine crops each cell centred on its declared width, the
generator grows the advance until the ink provably fits:

```python
while adv < src_w:
    half = adv * scale / 2
    if ink_left >= centre - half - extraL*scale and \
       ink_right <= centre + half + extraR*scale: break
    adv += 1
```

This is what makes the horn safe: it adds ink to the right of the base, and
the advance widens to accommodate it instead of the horn being silently
clipped.

---

## Thai — `ttfgen.build_thai`

### Sizing

Thai is sized off the Latin **x-height**, not cap height:

```python
target = bm["xheight"] * 1.15 * oversample
size = _fit_size(ttf, "ก", target)      # KO KAI
```

`ก` is an x-height-class letterform. Matching it to cap height makes Thai sit
visibly larger than the Latin beside it — this was the first attempt and it
looked wrong.

### Monospacing

Spacing glyphs are monospaced at the **median** advance of the Thai letters
(`unicodedata.category == 'Lo'`). Using `max()` monospaces the whole script to
the widest symbol in the block — a currency sign — and spaces Thai out
absurdly. The shipped `_Thai 16px` is also monospaced (`DefaultWidth=12`, no
per-frame widths).

Monospacing is not just aesthetic: it makes the combining-mark offset a single
known quantity.

### Combining marks

Marks (`category == 'Mn'`) get `width = 0` and rely on the engine's overlay
behaviour — the whole cell is drawn centred on the pen without advancing. See
[01](01-engine-internals.md#the-zero-width-overlay).

Each mark is isolated by rendering `base + mark` and `base` separately and
diffing the alpha channels:

```python
diff = ImageChops.difference(comp.alpha, base.alpha).point(lambda v: 255 if v > 40 else 0)
```

Two quantities are recorded from that diff:

- `dx` — the mark's ink centre relative to the **base glyph's** ink centre;
- `above` — how far the mark's top sits above the baseline (negative for the
  below-base vowels, which is what we want).

Placement then follows from the overlay geometry. The zero-width cell is
centred on the pen, and the pen sits just past the preceding consonant, whose
own glyph is centred on its advance box. So the mark's ink centre belongs at:

```
cell_w/2 - advance/2 + dx
```

and its top at `baseline - above`.

Sanity check against the shipped art: measuring `_Thai 16px [Sara2]` frames
gives offsets of −2.0 to −6.5 px from cell centre against a 12 px advance —
i.e. clustered around −advance/2, exactly as derived.

`DrawExtraPixelsLeft/Right` are set to the full cell width so the clamp always
resolves to `frameWidth/2` and the whole cell is drawn.

---

## Korean and Chinese — `ttfgen.build_cjk`

Both are the same problem: a large set of monospaced, roughly square glyphs.
`build_korean` and `build_chinese` are thin wrappers over `build_cjk`.

### Sets

| script | set | size |
|---|---|---|
| Korean | the full Hangul syllable block `U+AC00–U+D7A3` | 11,172 |
| Chinese | GB2312 ∪ Big5 Han, plus kana `U+3040–U+30FF` and CJK punctuation `U+3000–U+303F` | 15,697 |

Membership is computed with Python's own `gb2312` and `big5` codecs rather
than a hardcoded table.

**Why Chinese includes kana:** the page overrides the shipped JIS pages for
every codepoint it defines, which is most Japanese kanji too. A Han-only page
would leave Japanese titles half in this face at body size and half in the
larger JIS pages. Including kana keeps Japanese internally consistent.

### Sizing

```python
target = bm["cap"] * 1.12 * oversample
```

Ideographs read small at exactly cap height; 1.12 matches them to surrounding
Latin. The cell is then measured over a ~400-glyph sample so it fits the
extremes without measuring all 15,000.

### Coverage filtering

Any character the source font cannot draw is dropped and reported, so a font
with partial coverage degrades to "fewer glyphs" rather than a page of blanks:

```python
ok = font.getmask(ch).getbbox() or unicodedata.category(ch) == "Zs"
```

The whitespace exception matters: `U+3000` IDEOGRAPHIC SPACE legitimately has
no ink, and dropping it would send it to the blank *missing-glyph* fallback
instead of rendering as a space.

### Packing

Oversampling is chosen adaptively — the sharpest scale whose whole set still
fits within `max_pages` textures of `max_tex` square:

```python
for o in (3, 2, 1):
    if _cjk_pages(body, ttf, chars, o, max_tex, ref) <= max_pages:
        oversample = o; break
```

`max_tex` defaults to 2048 to match the common `MaxTextureResolution`
preference; exceeding it means the engine downscales the page and the result
is blurry. Pages beyond the first are named `p2`, `p3`, … — arbitrary names
are fine, since [page discovery](01-engine-internals.md#page-discovery) is
driven by the PNG filenames.

Typical result for Korean against Simply Love: oversample 1, source cell
17 × 22, two pages (2040 × 2046 and a 2040 × 22 sliver of 12 glyphs).
