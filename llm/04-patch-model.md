# 04 — The patch model

How `fontpatch.py` decides what to touch, and the guarantees it maintains.

---

## Discovery

`find_roots()` probes a list of standard install locations (and accepts
`--root`, repeatable). A candidate is kept only if it has `Themes/` **and**
either a usable theme or an existing manifest. The user data directory
(`%APPDATA%\ITGmania`) usually has an empty `Themes/`; skipping it stops
`verify` reporting a spurious failure there.

For each theme, `Target` resolves two things through that theme's search path
(`<theme>/Fonts`, then `_fallback/Fonts`):

| | |
|---|---|
| `common_default` | the `Common default` the theme actually resolves |
| `body` | `Common Normal`, falling back to `_open sans semibold 24px` |

`body` is the font Vietnamese is composited from and whose metrics everything
is matched to. `common_default` is the only file that gets modified.

### Shadowing

`Target.owns_common_default` is true when the resolved `Common default` lives
in the theme's own `Fonts/` rather than `_fallback`'s.

Install iterates themes with `_fallback` **first**, keyed by the resolved
`Common default` path. A theme that resolves to a path already handled is
reported as *covered by* and skipped — otherwise every inheriting theme would
rewrite `_fallback`'s file in turn.

Net effect on a stock install: `_fallback` is patched once as the shared
baseline, and Simply Love is patched separately because it ships its own copy
and shadows the chain.

---

## The edit

One line, appended to the `[main] import=` of the resolved `Common default`:

```diff
-import=16px fonts/_16px fonts
+import=16px fonts/_16px fonts,_Thai 16px,_korean 24px,_japanese 24px,_chinese 24px,_fontpatch vietnamese,_fontpatch thai,_fontpatch korean,_fontpatch chinese
```

Order within the line is deliberate:

1. **shipped language pages first** — `_Thai 16px`, `_korean 24px`,
   `_japanese 24px`, `_chinese 24px`. Simply Love's `_16px fonts` override
   pulls in CJK but omits Thai and Korean, so those glyphs ship with the game
   and are simply never reachable. Wiring them costs one import each and adds
   no files.
2. **generated pages last**, so they win where both define a character
   ([later imports override](01-engine-internals.md#import-resolution)).

`patch_import()` operates on **bytes**, detects the file's existing EOL and
preserves it, parses the existing comma list, and is a no-op if the entry is
already present. If `[main]` exists without an `import=` line, one is inserted.

### Why not `_16px fonts`

`_fallback/Fonts/_16px fonts.ini` advertises itself as the extension point and
would work. `Common default` is used instead because both `_fallback` and
Simply Love define it, so the patch shape is identical in both cases — whereas
`_16px fonts` is defined in `_fallback` and overridden by Simply Love at a
different relative path (`16px fonts/_16px fonts`).

---

## Generated files

Per theme, written next to the `Common default` being patched so they resolve
theme-first:

```
Fonts/_fontpatch vietnamese.ini
Fonts/_fontpatch vietnamese 10x10 (res 240x300).png
Fonts/_fontpatch thai.ini
Fonts/_fontpatch thai 16x6 (res 640x156).png
Fonts/_fontpatch korean.ini
Fonts/_fontpatch korean 120x93 (res 2040x2046).png
Fonts/_fontpatch korean [p2] 120x1 (res 2040x22).png
Fonts/_fontpatch chinese.ini
Fonts/_fontpatch chinese ... .png
```

The backup goes to `<root>/fontpatch-backup/<path of Common default>`, never
beside the original: `Font::GetFontPaths` globs `<name>*` and loads every
non-`.ini` hit as a texture page, so `Common default.ini.fontpatch-bak` in
`Fonts/` fails with "RageBitmapTexture: ... unknown file format" on launch.
`install` migrates and deletes such a file left by older versions.

`fontspec.write()` deletes any stale `_fontpatch <script>*.png` whose filename
no longer matches, so a regeneration at different geometry cannot leave an
orphan page behind — which would otherwise still be discovered and loaded,
since [pages are found by filename](01-engine-internals.md#page-discovery).

Because Simply Love's Vietnamese page is composited from Miso, and
`_fallback`'s from Open Sans, each theme gets glyphs in its own typeface.

---

## Idempotency

`install` **always re-patches from the backup**, never
from the current file. The backup is created on first install and never
overwritten. Consequences:

- repeated installs cannot stack duplicate imports;
- a half-finished run is recoverable by running it again;
- the backup is always the pristine theme file, so `uninstall` is exact.

Installing a subset (`--scripts thai`) merges into the manifest rather than
replacing it:

```python
prev = manifest["entries"].get(key, {})
all_scripts = dict(prev.get("scripts", {}))
all_scripts.update(generated)
```

Without this, a subset install drops the record of previously installed
scripts and `uninstall` orphans their files — a bug that was present and
fixed; see [06](06-extending.md#bug-log).

---

## The manifest

`<itgmania root>/fontpatch-manifest.json`, keyed by the normalised relative
path of the patched `Common default`:

```json
{
  "version": 2,
  "entries": {
    "themes\\simply love\\fonts\\common default.ini": {
      "theme": "Simply Love",
      "common_default": "Themes\\Simply Love\\Fonts\\Common default.ini",
      "backup": "fontpatch-backup\\Themes\\Simply Love\\Fonts\\Common default.ini",
      "body_font": "Themes\\Simply Love\\Fonts\\Miso\\_miso light.ini",
      "scripts": {
        "vietnamese": {
          "font": "_fontpatch vietnamese",
          "glyphs": 94,
          "source": "_miso light.ini",
          "files": ["..."],
          "sha": {"...": "..."},
          "unbuildable": []
        }
      },
      "extra_imports": ["_Thai 16px", "_korean 24px"],
      "failed": {}
    }
  }
}
```

It records what was installed, from which source font, and which glyphs could
not be built. It is the input to `uninstall` and part of what `verify` checks.

---

## `verify`

Four independent checks per entry:

1. every recorded generated file still exists;
2. the `Common default` still contains each generated font's import;
3. every glyph of each installed script is reachable through the theme's
   resolved coverage;
4. nothing in the song library's TITLE / SUBTITLE / ARTIST is still uncovered.

Check 2 is the one that catches a theme update. Check 4 is the one that
catches a newly added song using a character outside the generated sets.

Exit code is non-zero if anything failed, so it is usable in a script.

---

## `uninstall`

Restores each `Common default` from its backup, deletes the backup, deletes
every file recorded in the manifest, then deletes the manifest. Verified to
leave zero generated files and zero import references.

If the backup is missing it falls back to removing the import entries
individually, so a partially cleaned install still recovers.
