# 05 — Verification

The game is awkward to drive in a loop, so most verification here is offline:
read what was installed and reason about it the way the engine would.

Three layers, cheapest first.

---

## 1. Coverage analysis — `smfont.coverage()`

Walks the import graph exactly as `Font::Load` does and returns
`char -> (ini_path, page_name)` for everything a font can draw.

```python
cov = smfont.coverage("Common Normal", search_dirs)
missing = [c for c in title if c not in cov]
```

This is what `scan` and `verify` use. It proves **reachability** — that a
character resolves to some page — without touching pixels.

Two properties it must get right, both of which were wrong at some point:

- **Later imports override earlier ones** (`dict.update`, not `setdefault`),
  matching `MergeFont`. With `setdefault`, the shipped `_Thai 16px` would
  appear to win over our generated Thai page, and the preview would render
  the wrong one.
- **It returns resolved paths, not font stems.** A stem is not always
  resolvable — Simply Love keeps Miso at `Fonts/Miso/_miso light`, so
  `resolve("_miso light")` fails while `resolve("Miso/_miso light")`
  succeeds. Returning stems made the preview silently drop every ASCII
  character.

---

## 2. Geometry assertions

Before installing, the Vietnamese generator proves each glyph's ink fits the
window the engine will crop it to:

```python
half = adv * scale / 2
lo = centre - half - extraL * scale
hi = centre + half + extraR * scale
assert bbox[0] >= lo and bbox[2] <= hi
```

This is the check that makes horn letters safe — they add ink to the right of
the base and would otherwise be silently clipped. Run across all 94 glyphs it
reports `ALL glyphs fit inside their crop window`.

Equivalent reasoning covers the vertical axis: padding is derived by measuring
the composed glyphs rather than guessed, so stacked marks on capitals cannot
overflow the cell.

---

## 3. The offline renderer — `fontpatch.render()`

Reads the **installed** files and reproduces the engine's glyph pipeline:

| engine behaviour | reproduced |
|---|---|
| `(res WxH)` / `doubleres` source dimensions | yes |
| per-page `Baseline`, alignment on a common baseline | yes |
| centred crop to declared width (`SetTextureCoords`) | yes |
| `DrawExtraPixels` with the `+1`, even-rounding and clamp | yes |
| zero-advance overlay glyphs | yes |
| `AdvanceExtraPixels` | yes |
| later-import-wins page selection | yes (via `coverage`) |

```bash
python src/fontpatch.py preview --text "Vết Xước  แค่เธอ  르세라핌  爱财龙"
```

This is what catches real mistakes. Things it has actually caught:

- the hook-above mark rendering as a breve (wrong `?` cut);
- Thai sized to cap height instead of x-height, sitting visibly too large;
- ASCII vanishing from previews (the stem-vs-path bug above);
- CJK rendering much larger than the Latin around it.

### What it does **not** prove

- that the engine parses the ini identically — it is a reimplementation, and a
  second implementation of the same spec can be wrong in the same way;
- texture loading, `power_of_two` padding, or `MaxTextureResolution`
  downscaling;
- stroke/outline layers, which the tool neither generates nor simulates;
- anything about how a theme's Lua actually positions the text.

So "verified" in this repo means *the files parse, resolve and lay out
correctly under a faithful reimplementation*. It is not the same as "seen in
the game". Launching ITGmania and looking at the music wheel remains the only
true end-to-end check.

---

## Regression checks worth re-running after changes

```bash
# 1. clean round trip - must end with zero files and zero import refs
python src/fontpatch.py uninstall
python src/fontpatch.py install
python src/fontpatch.py verify          # expect exit 0

# 2. drift detection - simulate a theme update reverting the import line
cp "<root>/fontpatch-backup/Themes/<theme>/Fonts/Common default.ini" "<theme>/Fonts/Common default.ini"
python src/fontpatch.py verify          # expect exit 1, naming each lost import
python src/fontpatch.py install
python src/fontpatch.py verify          # expect exit 0

# 3. subset install must not orphan other scripts
python src/fontpatch.py install --scripts thai
python -c "import json;d=json.load(open('<root>/fontpatch-manifest.json'));
print([sorted(e['scripts']) for e in d['entries'].values()])"
# expect all four scripts still listed

# 4. generators still work across differently-shaped fonts
#    Miso Light (128px art, res hint), Open Sans (36px, no hint),
#    Roboto (28x36 non-square), frutiger (implicit cp1252, no breve-a)

# 5. legacy backup migration - nothing may be left beside Common default
cp "<root>/fontpatch-backup/Themes/<theme>/Fonts/Common default.ini" \
   "<theme>/Fonts/Common default.ini.fontpatch-bak"
python src/fontpatch.py verify          # expect exit 1, "old backup beside Common default"
python src/fontpatch.py install         # or: .\Repair-FontPatch.ps1
ls "<theme>/Fonts/Common default"*  # expect only Common default.ini

# 6. --root validation - must refuse before touching anything
python src/fontpatch.py verify --root C:\nope           # expect exit 2
.\Repair-FontPatch.ps1 -Root C:\nope                # expect exit 2
.\Repair-FontPatch.ps1 -WhatIf                      # expect only "What if:" lines, no changes
```

`Repair-FontPatch.ps1` must keep working in both Windows PowerShell 5.1 and
PowerShell 7; test it in both, since they differ in path validation errors and
`-WhatIf` propagation.

Check 4 matters because each of those fonts exercises a different branch of
`smfont.py`: oversampled art with a `res` hint, 1:1 art, non-square cells, and
implicit charmaps with missing primitives.
