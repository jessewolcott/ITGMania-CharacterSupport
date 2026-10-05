# 06 — Extending the tool

## Adding a new script

Worked example: adding Devanagari, Cyrillic-Extended, Greek — anything that is
a set of codepoints renderable from a TTF.

1. **Define the set** in `ttfgen.py`. Prefer deriving it from a codec or a
   Unicode block over a hardcoded list:

   ```python
   GREEK = [chr(c) for c in range(0x0370, 0x0400)]
   ```

2. **Pick a builder.** If the glyphs are monospaced and roughly square, reuse
   `build_cjk` — it already handles sizing, sampling, coverage filtering and
   multi-page packing:

   ```python
   def build_greek(body, ttf, chars=None, **kw):
       return build_cjk(body, ttf, chars or GREEK, ref="Ω",
                        notes=["Greek block."], **kw)
   ```

   If it is proportional, model it on `build_thai`, which measures per-glyph
   advances. If it has combining marks, read
   [03 — Thai](03-generators.md#thai) first: they need `width = 0` and a
   measured offset, not a naive overlay.

3. **Register it in `fontpatch.py`** in four places:

   ```python
   ALL_SCRIPTS = [..., "greek"]
   TTF_PREFS["greek"] = ["NotoSansGreek-Regular.ttf", ...]
   PROBE["greek"]     = "Ω"
   # script_chars() and _build_spec() each need a branch
   ```

4. **Add the CLI flags** — `--greek-font`, and `--greek-oversample` if it is a
   large set — and thread them through `opts`.

5. **Verify** with the checks in [05](05-verification.md), especially the
   preview, and against at least two differently-shaped body fonts.

Nothing else needs touching: `fontspec.write()`, the manifest, `verify` and
`uninstall` are all script-agnostic.

### If the script can be composited instead

Prefer it. If every glyph you need decomposes into pieces the theme's own font
already has, extend `compose.py` rather than adding a TTF dependency — the
result matches the typeface exactly and needs no source font. This is viable
for most Latin-script additions (Latin Extended-A, Esperanto, Turkish,
Romanian) because the base letters and marks are already present in any
Latin-1 + Latin-2 font.

---

## Pitfalls

**Widths are in source units.** Not image pixels. See
[02](02-font-file-format.md#resolution-hints). This is the single most common
way to produce a page that looks fine as a PNG and renders as slivers.

**Ink must be centred in its cell.** The engine crops centred on the declared
width. A left-aligned glyph loses its right side.

**`DrawExtraPixels` does not change the advance.** It widens what is drawn.
Use it for overhang, not spacing.

**Pages are discovered by filename, not by ini section.** An `[xyz]` section
with no matching PNG does nothing; a stale PNG with no section is still
loaded. Always clean up renamed pages — `fontspec.write()` does.

**Never write a non-page file beside a font.** Anything named `<font>*` that
is not an `.ini` is loaded as a texture, whatever its extension. Backups,
temp files and logs go outside `Fonts/`.

**Keep Pillow imports lazy in anything `fontpatch.py` imports at module top.**
Otherwise a missing Pillow crashes on import, before the friendly
"needs Pillow" message and before `--root` validation.

**PowerShell variable names are case-insensitive.** `$Manifest` and
`$manifest` are the same variable; give constants distinct names.

**Windows PowerShell 5.1 strips embedded double quotes from native-command
arguments.** `python -c 'print("ok")'` arrives as `print(ok)`. Avoid quotes
inside arguments passed to `python.exe`.

**Don't make a pass-through wrapper an advanced script.** `[CmdletBinding()]`
or any `[Parameter()]` attribute adds the common parameters, and prefix
matching then claims the wrapped tool's short flags (`-v`, `-o`).

**The embeddable Python ignores the script's directory.** `sys.path` comes
only from `python3XX._pth`; list every source directory there.

**Preserve line endings.** Reading a file with Python's universal newlines and
writing it back rewrites every EOL. Patch on bytes.

**A font's filename is not its licence.** Read the name table.

**Theme chain order is current-first.** Anything a theme defines shadows
`_fallback` completely — there is no merging of same-named files across
themes.

---

## Bug log

Real bugs hit while building this, kept because each one is a trap that is
easy to fall into again.

| bug | cause | fix |
|---|---|---|
| Coverage model preferred earlier imports | used `dict.setdefault` for imports | `MergeFont` assigns, so later wins — use `update` |
| Preview dropped all ASCII | `coverage()` returned font *stems*; `_miso light` lives in a subdirectory and does not resolve | return resolved paths |
| `dấu hỏi` rendered as a breve | cut the `?` where its row extent narrowed, keeping only the arc | take a fixed 58 % of the first ink band, arc + tail |
| Thai visibly oversized | sized to Latin cap height | size to x-height × 1.15; `ก` is x-height-class |
| Thai spaced absurdly wide | monospaced to `max()` advance over the whole block, which is a currency symbol | use the median advance of `category == 'Lo'` |
| Subset install orphaned other scripts | manifest entry replaced wholesale | merge `scripts` into the previous entry |
| CRLF file silently rewritten to LF | read with universal newlines, written back | patch on bytes, detect existing EOL |
| `U+3000` became a missing-glyph box | blank-ink filter dropped it | keep `category == 'Zs'` regardless of ink |
| `verify` failed on an empty user-data `Themes/` | treated every root as installable | skip roots with no usable theme and no manifest |
| `scan` reported "0 affected" while artists were broken | only checked `#TITLE` | check TITLE, SUBTITLE and ARTIST |
| Module name collided with a function | `render.py` vs the CLI's `render()` | renamed the module to `ttfgen.py` |
| Game failed to launch: `RageBitmapTexture: Couldn't load .../Common default.ini.fontpatch-bak: unknown file format` | backup written beside `Common default.ini`; `GetFontPaths` loads every non-`.ini` `<name>*` file as a page | backups moved to `<root>/fontpatch-backup/`; `install` / `Repair-FontPatch.ps1` migrate old ones |
| No "needs Pillow" message, just a traceback | `import compose` at module top pulled in Pillow before `main()` ran | import `compose` lazily where it is used |
| `--root` typo produced confusing output | explicit roots were never checked | `root_error()` / `-Root` validation, exit 2 |
| `uninstall` after a theme update restored the pre-update `Common default` | backup written once and never refreshed | refresh it whenever `Common default` carries none of our imports |
| `uninstall` with no backup left imports naming deleted fonts | docs promised a fallback the code never had | strip each recorded import with `patch_import(remove=True)` |
| `uninstall --theme X` removed every theme | `--theme` was accepted but ignored by `verify` / `uninstall` | `selected_entries()`; manifest kept until empty |
| `install --root` on a root with no usable theme printed nothing, exit 0 | unpatchable roots were skipped silently | report it; `install` exits 1 |
| `preview` said "nothing to render" without Simply Love | default theme hardcoded | fall back to the first patchable theme, report an unknown one |
| `Repair-FontPatch.ps1 -WhatIf` crashed on 5.1 | `Get-FileHash` honours `-WhatIf` and returns nothing | hash with .NET `SHA256` directly |
| Message printed `python srcontpatch.py` | `sed` read `\f` in `src\fontpatch` as a form feed | write backslashes from Python, not `sed` replacements |
| `scan --theme X` still listed every theme | `cmd_scan` looped over `themes_of(root)` | loop over `args.theme or themes_of(root)` |
| Private runtime failed its self-test on 5.1 | `-c 'print("ok")'` lost its quotes on the way to `python.exe` | quote-free self-test, rely on the exit code |
| `Install-FontPatch.ps1 preview -o out.png` failed: `-o` ambiguous | `[CmdletBinding()]` added `-OutVariable` / `-OutBuffer` | plain script, extra arguments taken from `$args` |
| PowerShell repair wrote a file named `@{version=2; entries=}` | `$manifest` (data) overwrote `$Manifest` (filename) — PS names are case-insensitive | renamed the constant to `$ManifestFile` |

---

## Things deliberately not done

- **No upstreaming.** This is a standalone patcher by design. It generates
  pages locally from fonts the user already has, so no font data is
  redistributed and there is no licensing question. Committing generated pages
  to a repository would reintroduce one — they are `.gitignore`d.
- **No modification of theme font files.** Only `Common default.ini` is
  touched, and a backup is kept outside the theme. Pages are added alongside,
  never merged into an existing font.
- **No size-matched Japanese page.** The shipped JIS pages render larger than
  the Latin text. The Chinese page fixes this for everything it covers
  (GB2312 ∪ Big5 + kana); rare Han outside that still falls back to JIS and
  still looks oversized. Covering all of JIS X 0212 would roughly double the
  generated data for a small gain.
- **No text shaping.** The engine has none, so neither does this. Thai uses
  the engine's own overlay convention; complex scripts that genuinely require
  reordering or ligatures (Devanagari, Arabic) cannot be done correctly as
  bitmap pages and should not be attempted.
