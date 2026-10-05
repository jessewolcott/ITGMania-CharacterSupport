# Technical documentation

Deep notes on how this patcher works and, more importantly, on the engine
behaviour it depends on. Most of what follows is not stated anywhere in the
StepMania/ITGmania source — it was derived by reading `src/Font.cpp`,
`src/RageBitmapTexture.cpp` and `src/ThemeManager.cpp` and confirming against
the shipped font assets.

Read in order if you are new:

| doc | covers |
|---|---|
| [01-engine-internals.md](01-engine-internals.md) | how the engine loads fonts, resolves names, merges imports, and positions glyphs |
| [02-font-file-format.md](02-font-file-format.md) | the `.ini` + `.png` format exactly as parsed, including undocumented behaviour |
| [03-generators.md](03-generators.md) | the glyph generation algorithms — compositing, Thai overlays, CJK packing |
| [04-patch-model.md](04-patch-model.md) | install/verify/uninstall semantics, idempotency, the manifest |
| [05-verification.md](05-verification.md) | the offline renderer, what it proves and what it cannot |
| [06-extending.md](06-extending.md) | adding a script, plus a log of bugs already hit and why |

## The five facts that matter most

If you read nothing else, these are the non-obvious engine behaviours that
every generator in this repo is built around.

1. **`Common default` is imported behind every font.** `Font::Load` pushes it
   onto the import list for any top-level font. One import line there reaches
   the entire theme. See [01](01-engine-internals.md#import-resolution).

2. **Later imports win; the font's own pages win over all imports.**
   `MergeFont` assigns into `m_iCharToGlyph`, it does not `setdefault`. This is
   what lets our pages override the shipped ones without touching them.

3. **Glyph widths are in *source-resolution* units, not image pixels.** A
   `(res WxH)` filename hint overrides the texture's apparent size, so a
   1920×1920 page declared `(res 360x360)` has 24-unit cells even though the
   art is 128 px. Getting this wrong silently produces glyphs cropped to a
   sliver. See [02](02-font-file-format.md#resolution-hints).

4. **Each cell is cropped *centred* on its declared width**, then widened by
   `DrawExtraPixels` clamped to `(frameWidth - charWidth)/2`. Ink outside that
   window is invisible. Generators must prove the ink fits.

5. **`m_fVshift = -iBaseline`**, so a cell is positioned by its baseline, not
   its top. A taller cell with a correspondingly larger `Baseline` costs
   nothing and buys headroom — which is how stacked Vietnamese tone marks fit
   above capitals without changing line height.

## Invariants this repo maintains

Any change should preserve all of these:

- The theme's own font files are never modified. Only `Common default.ini`
  gains an import line, and a backup of it is kept under `<root>/fontpatch-backup/`
  (never in `Fonts/`, where the engine would load it as a texture page).
- `install` is idempotent and always re-patches from the backup, never from
  the current file, so repeated runs cannot stack imports.
- Installing a subset of scripts never orphans previously installed ones (the
  manifest is merged, not replaced).
- `uninstall` restores the backup and removes every generated file, leaving no
  trace.
- Generated pages never leave the user's machine — they are derived from
  locally installed fonts and are `.gitignore`d.
- Line height is preserved: `Baseline - Top` on a generated page equals the
  body font's.
