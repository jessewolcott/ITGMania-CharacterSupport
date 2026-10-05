# ITGMania-CharacterSupport

**Make Vietnamese, Thai, Korean and Chinese song titles show up in ITGmania.**

If some of your song titles, subtitles or artists show up blank, cut off, or
missing their accents, it isn't your simfiles: the theme's fonts just don't
have those characters. This tool adds them using fonts already on your
computer, and it can be undone at any time.

![song titles rendering correctly after the patch](docs-preview.png)

- Works with **Simply Love** and any theme built on ITGmania's `_fallback`
- Builds the new characters **on your PC** from fonts you already have.
  Windows ships everything it needs
- **No Python install needed** on Windows: one PowerShell command does it all
- Changes **one line** per theme and keeps a backup. `uninstall` puts it all back

---

## Quick start

> **Close ITGmania before you start.** It only reads fonts at launch.

First, get the files: on the
[GitHub page](https://github.com/jessewolcott/ITGMania-CharacterSupport) click
**Code → Download ZIP**, then unzip it anywhere. Or clone it:

```
git clone https://github.com/jessewolcott/ITGMania-CharacterSupport.git
```

Then choose one of the two paths below. Both do exactly the same thing and
produce identical results.

### Option A: PowerShell, no Python needed (Windows, recommended)

1. **Open PowerShell in the unzipped folder.** In Explorer, open the folder,
   right-click an empty spot and choose **Open in Terminal**.
2. **Install:**
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\Install-FontPatch.ps1
   ```
   The first run downloads a private copy of Python (about 40 MB) into a
   `.runtime` folder inside the tool's folder. It takes a few seconds. Nothing
   is installed on your system, and later runs reuse it with no download.
3. **Check it worked:**
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\Install-FontPatch.ps1 verify
   ```
   Every line should say `[OK ]`.
4. **Launch ITGmania** and look at the music wheel.

`-ExecutionPolicy Bypass` lets Windows run a script downloaded from the
internet for this one run only. It doesn't change any settings.

Every Python command below works the same way through this script: replace
`python src/fontpatch.py` with
`powershell -ExecutionPolicy Bypass -File .\Install-FontPatch.ps1`.
For example, `... scan -v` or `... uninstall`.

<details>
<summary>What exactly does it download?</summary>

The official embeddable Python 3.13 build from python.org, plus the Pillow and
fonttools packages from PyPI. The versions are pinned in the script, and every
file is checked against a pinned SHA-256 hash before use. If a hash doesn't
match, the download is refused. To remove the private copy, delete the
`.runtime` folder, or run the script with `-Clean`.
</details>

### Option B: Python (if you already use it, or on macOS/Linux)

1. **Install Python 3** from [python.org](https://www.python.org/downloads/)
   if you don't already have it. On Windows, tick **"Add python.exe to PATH"**
   in the installer.
2. **Open a terminal in the unzipped folder.**
3. **Install the one dependency:**
   ```
   python -m pip install -r requirements.txt
   ```
4. **Install:**
   ```
   python src/fontpatch.py install
   ```
5. **Check it worked:**
   ```
   python src/fontpatch.py verify
   ```
6. **Launch ITGmania** and look at the music wheel.

If `python` isn't recognised on Windows, use `py` instead (for example
`py src/fontpatch.py install`).

Want to see what's missing first without changing anything? Run `scan`
(`python src/fontpatch.py scan`, or `... Install-FontPatch.ps1 scan`).

### Is your game somewhere unusual?

The tool looks in the usual places on its own:

- `C:\Games\ITGmania`
- `C:\Program Files\ITGmania`
- `%APPDATA%\ITGmania`
- `~/.itgmania`
- `~/Library/Application Support/ITGmania`
- `/opt/itgmania`

If yours is somewhere else, point the tool at it. Use the folder that contains
`Themes`:

```
powershell -ExecutionPolicy Bypass -File .\Install-FontPatch.ps1 -Root "D:\Games\ITGmania"
python src/fontpatch.py install --root "D:\Games\ITGmania"
```

If the folder doesn't exist or has no `Themes` folder, the tool stops and
tells you why before changing anything.

---

## After a theme update

Updating a theme (for example a new Simply Love release) resets its font
settings, so the characters go missing again. The pages the tool built are
still there, so just run the install again:

```
powershell -ExecutionPolicy Bypass -File .\Install-FontPatch.ps1
python src/fontpatch.py install
```

(Use whichever one you used before.) `verify` shows what the update undid.

---

## Undo everything

```
powershell -ExecutionPolicy Bypass -File .\Install-FontPatch.ps1 uninstall
python src/fontpatch.py uninstall
```

This restores each theme's original font settings and deletes everything the
tool created. To undo just one theme, add `-Theme "Simply Love"` (PowerShell)
or `--theme "Simply Love"` (Python).

---

## Troubleshooting

### The game won't start: "unknown file format"

```
RageBitmapTexture: Couldn't load /Themes/Simply Love/Fonts/Common default.ini.fontpatch-bak: unknown file format
```

An older version of this tool kept its backup inside the theme's `Fonts`
folder, and ITGmania tries to load anything in there that's named like a font.
Running the install again moves the backup to a safe place
(`<your ITGmania folder>\fontpatch-backup\`). So does `Repair-FontPatch.ps1`,
a small repair-and-check script that doesn't download anything:

```
powershell -ExecutionPolicy Bypass -File .\Repair-FontPatch.ps1
```

### "No ITGmania install found"

Your game isn't in one of the usual places. Add `-Root` (PowerShell) or
`--root` (Python) with the folder that contains `Themes`. See
[Is your game somewhere unusual?](#is-your-game-somewhere-unusual)

### "Setup failed" from Install-FontPatch.ps1

The first run needs internet access to python.org and pypi.org. Check your
connection, firewall or proxy and run it again. A failed setup never leaves a
half-finished copy behind. If you see "Checksum mismatch", the download was
corrupted or tampered with and was refused; try again later.

### "This tool needs Pillow"

You're using Option B. Run `python -m pip install -r requirements.txt` from
the unzipped folder, or switch to Option A, which handles this for you.

### "running scripts is disabled on this system"

Windows blocks downloaded scripts by default. Start the script the way the
quick start shows, with `powershell -ExecutionPolicy Bypass -File ...`.

### Some characters are still blank

Run `scan -v`. It lists every title, subtitle and artist that still won't
display, and which characters are missing. If a whole script was skipped
during install, the installer says why. Usually no suitable font was found,
and you can point it at one yourself:

```
powershell -ExecutionPolicy Bypass -File .\Install-FontPatch.ps1 install --thai-font "C:\path\to\SomeThaiFont.ttf"
python src/fontpatch.py install --thai-font "C:\path\to\SomeThaiFont.ttf"
```

---

## Command reference

### `python src/fontpatch.py <command>` or `.\Install-FontPatch.ps1 <command>`

The two are interchangeable. `Install-FontPatch.ps1` runs the same Python
tool using its private copy of Python, and passes every option through.

| command | what it does |
|---|---|
| `scan` | Shows which characters each theme is missing and which songs are affected. Add `-v` to list them. Changes nothing. |
| `install` | Builds the missing characters and adds them to each theme. Safe to run again any time. |
| `verify` | Checks the install is complete and still intact. Exits non-zero if not. |
| `preview` | Saves a picture of text rendered with the installed fonts, so you can check without launching the game. |
| `uninstall` | Restores everything and removes everything the tool created. |

Options:

| option | works with | meaning |
|---|---|---|
| `--root PATH` | all | your ITGmania folder (repeatable). It is checked before anything runs |
| `--theme NAME` | all | only this theme (repeatable) |
| `--scripts vietnamese,thai,korean,chinese` | `install` | install only some scripts. Ones already installed are kept |
| `--thai-font` / `--korean-font` / `--chinese-font PATH` | `install` | use a specific font file |
| `--korean-oversample` / `--chinese-oversample N` | `install` | texture sharpness. The default picks the sharpest that fits |
| `--no-extra-scripts` | `install` | don't connect the Thai/Korean/CJK fonts that already ship with the game |
| `--text "..."` / `-o FILE` | `preview` | text to render (defaults to your song titles) and the output file |
| `-v` | `scan` | list the affected songs |

```
$ python src/fontpatch.py scan -v
=== C:\Games\ITGmania
  Simply Love   viet 0/94  thai 0/95  kore 246/11172  chin 5756/15697  affected title/subtitle/artist: 15
        TITLE     Vết Xước                       missing: ếướ
        ARTIST    李要红RedLi                      missing: 红
```

`Install-FontPatch.ps1` also accepts PowerShell-style names for the common
options, plus one of its own:

| option | same as |
|---|---|
| `-Root PATH` | `--root PATH` |
| `-Theme NAME` | `--theme NAME` |
| `-Scripts thai,korean` | `--scripts thai,korean` |
| `-Clean` | delete the private Python copy (`.runtime\`) and exit |

With no command it runs `install`. It works in Windows PowerShell 5.1 and
PowerShell 7 on Windows.

### `.\Repair-FontPatch.ps1` (check and repair only)

A small standalone script that downloads nothing and doesn't use Python. It
can't add characters, but it can check an install and move old backups out of
the way.

| option | meaning |
|---|---|
| `-Root PATH` | your ITGmania folder (repeatable). It is checked before anything runs |
| `-Theme NAME` | only check this theme |
| `-WhatIf` | show what would be moved without changing anything |

The script works in Windows PowerShell 5.1 and PowerShell 7. It checks that:

- no stray file sits next to a font where the game would try to load it
- the backup is in the right place
- every generated font file is present, unchanged and a valid image
- every import line is still in the theme's font settings

It exits 1 if anything is wrong, so it can be used in other scripts.

---

## How it works

### Why the characters are missing

Song titles are stored as UTF-8, and ITGmania never strips accents. When a
character shows up blank, the theme's bitmap font simply has no picture for
it. Each script is missing for a different reason:

| Script | What's actually wrong |
|---|---|
| **Vietnamese** | No glyphs at all for `U+1EA0–U+1EF9`, nor for the horn letters `Ơ ơ Ư ư`. Latin-1 accents work, so `CHÁY MÁY` renders but `Vết Xước` does not. |
| **Thai** | `_Thai 16px` ships in `_fallback` but Simply Love never imports it. Even when it is reached, it uses `Baseline=36 / LineSpacing=36` against a body font at `19 / 24`. |
| **Korean** | The shipped `_korean 24px` pages are named `[jamo 1..4]` but contain no jamo. They hold ~246 hand-picked precomposed syllables, and most Hangul is simply absent. |
| **Chinese** | There is no Chinese font. `_chinese 24px` is 126 hand-picked UI words (`鍵輯按箭這玩…`) for translating the StepMania interface. Chinese text is drawn by the **Japanese JIS kanji** pages, which cover most traditional forms and almost no PRC-simplified ones. |

Measured against a stock install, before patching:

```
Big5   (traditional common)  13,061 chars →  5,554 covered,  7,507 missing (57%)
GB2312 (simplified common)    6,763 chars →  3,390 covered,  3,373 missing (50%)
Hangul syllables             11,172 chars →    246 covered, 10,926 missing (98%)
Vietnamese                       94 chars →      0 covered,     94 missing
```

### What it changes

Per theme, **exactly one file is modified**: one import line is appended to
`Common default.ini`:

```diff
-import=16px fonts/_16px fonts
+import=16px fonts/_16px fonts,_Thai 16px,_korean 24px,_japanese 24px,_chinese 24px,_fontpatch vietnamese,_fontpatch thai,_fontpatch korean,_fontpatch chinese
```

Everything else is added alongside the theme's files:

| path | |
|---|---|
| `Fonts/_fontpatch <script>.ini` + `.png` pages | generated font pages |
| `<itgmania root>/fontpatch-backup/Themes/<theme>/Fonts/Common default.ini` | backup, used by `uninstall`. It is kept outside the theme because the game loads any `Common default*` file in `Fonts/` as a texture |
| `<itgmania root>/fontpatch-manifest.json` | record of what was installed |

The theme's own fonts (such as `Miso/_miso light.ini` in Simply Love) are
**never touched**. Disk cost is roughly 6 MB per theme, almost all of it the
Chinese pages.

The backup is refreshed whenever `install` finds an unpatched
`Common default.ini`, for example after a theme update. That way `uninstall`
always restores the theme version you actually have. If a backup is missing,
`uninstall` removes the import entries one by one instead.

### Why `Common default`

ITGmania imports `Common default` behind **every** font, so one import line
reaches the whole theme. A font's own glyphs always take priority over
imported ones, so the patch can only fill gaps. It can never change something
that already displays.

The generated pages are imported *after* the shipped language pages, so where
both define a character, the generated one is used. `MergeFont` assigns into
`m_iCharToGlyph`, so the later import wins.

### `_fallback` and themes that override it

Patching `Themes/_fallback` fixes every theme that inherits from it. But a
theme that ships its own `Common default.ini` **overrides** `_fallback`'s copy
(`ThemeManager::GetPathInfoToAndFallback` checks the current theme first).
Simply Love ships its own, which is why it was missing Thai and Korean even
though both pages already existed in `_fallback`.

So the tool patches `_fallback`, plus each theme that overrides it. Themes that
inherit are detected and not patched twice.

### Where the characters come from

**Vietnamese is built from the theme's own letters**, so it needs no extra font
and matches the typeface exactly. Base letters and the acute, grave, tilde,
circumflex and breve marks are lifted from the font's own accented letters.
`dấu hỏi` is built from the bowl of its `?`, dot-below from its `.`, and the
horn from its `’`.

**Thai, Korean and Chinese can't be built from Latin shapes**, so they are
rendered from a font installed on your computer and sized to match the theme.
The tool tries these in order:

| script | preferred source |
|---|---|
| Thai | Noto Sans Thai, Sarabun, Niramit, Leelawadee UI, Tahoma |
| Korean | NanumGothic, Noto Sans KR, Malgun Gothic |
| Chinese | Noto Sans SC, Microsoft YaHei, SimSun |

Windows includes Leelawadee UI, Tahoma, Malgun Gothic and Microsoft YaHei, so
no download is needed. Override any choice with `--thai-font` /
`--korean-font` / `--chinese-font`.

The generated `.ini` records which font was used and its licence, read from
the font file itself rather than guessed from its name. That matters: the
NanumGothic build that ships with Windows is named like the OFL release, but
its name table says `NHN Corporation`.

**This repository contains no font data.** Pages are built on your machine
from fonts you already have, so there is no licensing question. That's also
why generated pages are `.gitignore`d and shouldn't be committed or shared.

### Chinese includes kana, on purpose

The Chinese page covers GB2312 ∪ Big5 Han **plus kana and CJK punctuation**.
It replaces the JIS pages for every character it defines, which includes most
Japanese kanji. A Han-only page would leave Japanese titles half in this face
at body size and half in the larger JIS pages. Including kana keeps Japanese
consistent. It also fixes the long-standing problem of CJK text looking
noticeably bigger than the Latin text next to it.

---

## Known limitations

- **Simplified vs Traditional regional forms.** A bitmap font maps one
  character to one picture, so where the two conventions draw a shared
  character differently, one style has to win. Noto Sans **SC** is the default
  because it also covers the Big5 traditional set, whereas a TC font is
  missing ~1,900 simplified-only forms. Use `--chinese-font` to flip it.
- **Rare Han outside GB2312 ∪ Big5** still falls back to the JIS pages, so it
  still looks larger than the text around it.
- **No text shaping.** The engine has none. Thai combining marks use the
  engine's zero-advance overlay convention, the same one the shipped Thai page
  uses.
- **Fonts missing the needed pieces.** `frutiger 24px` has no breve-`a`, so 10
  of the 94 Vietnamese characters can't be built from it. The tool lists them
  and installs the other 84.
- **`MaxTextureResolution`** (2048 by default) shrinks any larger page.
  Generated CJK pages are packed to stay inside it at the sharpest size that
  fits.
- **`preview` is a simulation.** It reproduces the engine's glyph layout
  rather than running the game. It proves the files load and line up, but
  launching ITGmania is the real test. See `llm/05-verification.md`.

---

## Project layout

| file | |
|---|---|
| `src/fontpatch.py` | the command-line tool: scan / install / verify / uninstall / preview |
| `src/smfont.py` | reader for StepMania bitmap fonts: redirs, imports, `Line`/`map`/`range`, `(res WxH)` hints |
| `src/compose.py` | Vietnamese builder (uses the theme's own font) |
| `src/ttfgen.py` | Thai / Korean / Chinese renderers (use a TTF) |
| `src/fontspec.py` | shared writer for `.ini` + `.png` font pages |
| `Install-FontPatch.ps1` | runs the tool with a private, auto-downloaded Python, so nothing needs installing |
| `Repair-FontPatch.ps1` | PowerShell backup repair + font check, no download and no Python |
| `requirements.txt` | Pillow, plus optional fonttools |
| `llm/` | in-depth technical documentation |

**Contributing, or pointing an AI assistant at this repo?** Start with
[`llm/README.md`](llm/README.md). It documents the engine behaviour the tool
depends on, most of which isn't obvious from the StepMania source.
