# 01 — Engine internals

Everything here is behaviour of the StepMania 5 / ITGmania font pipeline,
derived from `src/Font.cpp`, `src/FontManager.cpp`, `src/RageBitmapTexture.cpp`
and `src/ThemeManager.cpp`.

---

## Name resolution

A font is requested by name (e.g. `Common Normal`), never by path.
`THEME->GetPathF("", name, true)` resolves it through
`ThemeManager::GetPathInfoToAndFallback`, which iterates `g_vThemes` — the
theme fallback chain — and returns the **first** hit.

```
g_vThemes = [ current theme, FallbackTheme, ..., _fallback ]
```

The chain is built in `ThemeManager::LoadThemeMetrics`, which reads
`FallbackTheme` from `metrics.ini [Global]`; if absent, a theme falls back to
`_fallback` (`SpecialFiles::BASE_THEME_NAME`) unless it declares
`IsBaseTheme=1`.

**Consequence that drives this whole tool:** current theme wins. If Simply Love
ships `Fonts/Common default.ini`, the `_fallback` copy is never consulted — so
anything wired up only in `_fallback` is invisible to Simply Love.

### `.redir` indirection

If resolution lands on `<name>.redir`, the file's contents are a new font name
and resolution restarts. Chains are common:

```
Common Normal.redir  ->  "Miso/_miso light"   (Simply Love)
Common Normal.redir  ->  "_open sans semibold 24px"   (_fallback)
```

Note the target may contain a subdirectory. A font's *stem* is therefore not
necessarily resolvable on its own — `_miso light` does not resolve, only
`Miso/_miso light` does. `smfont.coverage()` returns resolved **paths** for
this reason; returning stems was a real bug (see
[06](06-extending.md#bug-log)).

---

## Import resolution

In `Font::Load`:

```cpp
bool bIsTopLevelFont = LoadStack.size() == 1;
if (bIsTopLevelFont) ImportList.push_back("Common default");
ini.GetValue("main", "import", imports);   // appended after
split(imports, ",", ImportList, true);

for (i : ImportList) { Font subfont; subfont.Load(...); MergeFont(subfont); }
// ... then this font's own pages are loaded
```

Three things follow:

1. **`Common default` is behind every top-level font.** This is the hook the
   patcher uses: appending to its `import=` line reaches every font in the
   theme, including the body font used for song titles.

2. **Order matters, and later wins.** `MergeFont` does:

   ```cpp
   for (it : f.m_iCharToGlyph) m_iCharToGlyph[it->first] = it->second;
   ```

   A plain assignment. So import *N+1* overrides import *N*. The patcher
   appends its pages after the shipped language pages precisely so ours win.

3. **The font's own pages override every import**, because they are loaded
   after the merge loop. A theme's existing glyphs can therefore never be
   displaced by an import — the patch can only fill gaps.

`_fallback/Fonts/_16px fonts.ini` is a "virtual font": no textures, only an
import list. Its own comment says themes may overload it to pull extra fonts
into every 16-pixel font. That is a legitimate alternative hook, but
`Common default` is used here because it is the one both `_fallback` and
Simply Love already define, so the patch shape is identical for both.

---

## Page discovery

`Font::Load` does not read page names from the ini. It scans the ini's
directory for textures whose filename stem matches, and derives the page name
from the bracketed tag:

```
_miso light 15x15 (res 360x360).png              -> page "main"
_miso light [alt] 10x10 (res 240x240).png        -> page "alt"
_miso light [alt-stroke] 10x10 (...).png         -> ignored (stroke layer)
```

So **a page exists because a PNG exists**, and its `[section]` in the ini only
supplies metrics. Writing an ini section with no matching PNG does nothing.

The scan is a plain prefix glob, and it does not filter by extension:

```cpp
// Font::GetFontPaths
GetDirListing(sPrefix + "*", asFiles, false, true);
for (...) if (!asFiles[i].Right(4).EqualsNoCase(".ini")) asTexturePathsOut.push_back(asFiles[i]);
```

**Every file in the folder whose name starts with the font's name and is not
an `.ini` is handed to `RageBitmapTexture` as a page.** A backup such as
`Common default.ini.fontpatch-bak` (or a stray `.txt`, `.bak`, `.orig`) beside
`Common default.ini` fails on launch with
`RageBitmapTexture: Couldn't load ... unknown file format`. Nothing this repo
writes may share a font's name prefix inside `Fonts/` unless it is a real page.

`WxH` in the filename is **frames wide × frames high**, not pixels.

---

## Texture dimensions and the `(res WxH)` hint

`RageBitmapTexture::Create` sets:

```cpp
m_iSourceWidth = pImg->w;          // actual image pixels
...
GetResolutionFromFileName(actualID.filename, m_iSourceWidth, m_iSourceHeight);
if (hint contains "doubleres") { m_iSourceWidth /= 2; m_iSourceHeight /= 2; }
```

`GetResolutionFromFileName` matches:

```cpp
Regex("\\([^\\)]*res ([0-9]+)x([0-9]+).*\\)")
```

so `(res 240x300)` is valid, non-square is fine, and it may be combined with
other hints inside the same parentheses (`(dither, res 512x128)`).

**This is the single most error-prone part of the format.** After this call,
"source" dimensions are the *declared* ones, and `GetSourceFrameWidth()` is
`sourceWidth / framesWide`. Every width in the ini is expressed in those units.

Worked example — Simply Love's Miso Light:

| | |
|---|---|
| image | 1920 × 1920 px |
| grid | 15 × 15 frames |
| art cell | 128 × 128 px |
| `(res 360x360)` → source | 360 × 360 |
| **source frame** | **24 × 24** |
| `Baseline=19` | 19 of those 24 units, i.e. 101 px into the art cell |

A width of `9` therefore means 9/24 of the cell, not 9 px.

Two further constraints:

- `m_iTextureWidth = power_of_two(m_iImageWidth)` — pages are padded up to a
  power of two in VRAM.
- `ID.iMaxSize = min(ID.iMaxSize, m_Prefs.m_iMaxTextureResolution)` — the
  `MaxTextureResolution` preference (commonly 2048) **downscales** anything
  larger. Several stock Japanese pages are 3528 × 3456 and are already being
  downscaled on such setups. Generated pages are packed to stay under it.

---

## Vertical metrics

`FontPage::Load`:

```cpp
m_iLineSpacing = cfg.m_iLineSpacing;
if (m_iLineSpacing == -1) m_iLineSpacing = GetSourceFrameHeight();

iBaseline = cfg.m_iBaseline;                 // default: centred in the frame
iTop      = cfg.m_iTop;
m_iHeight = iBaseline - iTop;
m_fVshift = (float)-iBaseline;               // <-- key line
```

`m_fVshift = -iBaseline` means the glyph quad is shifted up by `Baseline`, so
**the cell's y = Baseline lands on the text baseline**. The cell top is
wherever it happens to be.

This gives a free lever: make the cell taller, increase `Baseline` by the same
amount, and the glyphs land in exactly the same place with extra room above.
Shift `Top` too and `m_iHeight` (`Baseline - Top`) is unchanged, so
`GetLineHeightInSourcePixels` — which takes the max `m_iHeight` across the
glyphs on a line — is unaffected. That is how Vietnamese stacked tone marks fit
above capitals without altering line height.

`LineSpacing` is **not** derived from the cell; set it explicitly to the body
font's value or lines will jump when a generated glyph appears.

---

## Horizontal metrics: cropping

Two functions act in sequence on every glyph.

### `FontPage::SetTextureCoords`

```cpp
g.m_fWidth    = widths[i];
g.m_fHeight   = GetSourceFrameHeight();
g.m_iHadvance = int(g.m_fWidth) + iAdvanceExtraPixels;

int chop = GetSourceFrameWidth() - widths[i];
if (chop % 2 == 1) { --chop; ++g.m_fWidth; }   // keep texel alignment
g.m_TexRect.left  += chop/2 * ratio;
g.m_TexRect.right -= chop/2 * ratio;
```

The cell is cropped **centred**: `(frameWidth - width)/2` is removed from each
side. So glyph ink must be horizontally centred in its cell — the declared
width is a window around the cell centre, not a left-aligned box.

Odd leftovers are rounded so glyphs "err to being a pixel off-centre left".

### `FontPage::SetExtraPixels`

```cpp
iDrawExtraPixelsRight++;  iDrawExtraPixelsLeft++;
if (iDrawExtraPixelsLeft % 2 == 1) ++iDrawExtraPixelsLeft;

float fExtraLeft  = min(iDrawExtraPixelsLeft,  (iFrameWidth - fCharWidth)/2.0f);
float fExtraRight = min(iDrawExtraPixelsRight, (iFrameWidth - fCharWidth)/2.0f);

m_TexRect.left  -= fExtraLeft  * ratio;
m_TexRect.right += fExtraRight * ratio;
m_fHshift       -= fExtraLeft;
m_fWidth        += fExtraLeft + fExtraRight;
```

Note both the `++` on entry and the clamp. The visible window for a glyph is:

```
[ centre - width/2 - extraLeft ,  centre + width/2 + extraRight ]
```

with `extraLeft/Right ≤ (frameWidth - width)/2`. Crucially the **advance is
unchanged** — extra pixels widen what is drawn, not how far the pen moves.

### The zero-width overlay

Set `width = 0` and the clamp becomes `(frameWidth - 0)/2 = frameWidth/2`. With
a large `DrawExtraPixels`, the entire cell is drawn, `m_fHshift` is
`-frameWidth/2`, and `m_iHadvance` is `0`.

**The whole cell is painted centred on the pen, and the pen does not move.**

This is the engine's only mechanism for combining marks — there is no text
shaping anywhere. The shipped `_Thai 16px [Sara2]` page uses exactly this: all
widths `0`, `DrawExtraPixelsLeft/Right = 128`. Because the cell is centred on
the pen (which sits just *past* the preceding consonant), the mark art must be
drawn left of cell centre to land over that consonant. See
[03](03-generators.md#thai).

---

## Missing glyphs

`Font::GetGlyph` falls back to `FONT_DEFAULT_GLYPH` when a character has no
entry, which is supplied by `Common default` (`map default=0`). It renders as
a blank. There is **no** warning logged, which is why a coverage gap looks like
mysteriously absent characters rather than an error.

Also note `Font::Load` warns only if a top-level font has neither textures nor
imports; a virtual font with imports is fine.
