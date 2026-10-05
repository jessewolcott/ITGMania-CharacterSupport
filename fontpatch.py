# -*- coding: utf-8 -*-
"""fontpatch - fill in missing scripts in StepMania / ITGmania theme fonts.

Song titles are stored as UTF-8 and the engine never strips diacritics; the
bundled bitmap fonts simply have no glyphs for some scripts. This tool
generates the missing pages and wires them in.

  vietnamese  composited from the theme's own letterforms (no source font)
  thai        rendered from a Thai TTF, sized to the theme's body font
  korean      full precomposed Hangul block, likewise

How the wiring works
--------------------
`Common default` is imported behind *every* font by Font::Load, so appending to
its `import=` line reaches the whole theme. Imports load first and are then
overridden by the font's own pages, so a theme's existing glyphs always win.

_fallback is the shared home and covers every theme that inherits it. A theme
that ships its own Common default (Simply Love does) shadows that chain and
needs its own import line - `install` works this out per theme and `verify`
re-checks it after a theme update.

Usage
-----
    python fontpatch.py scan
    python fontpatch.py install [--scripts vietnamese,thai,korean]
    python fontpatch.py verify
    python fontpatch.py uninstall
    python fontpatch.py preview --text "..."
"""
from __future__ import print_function

import argparse
import glob
import hashlib
import json
import os
import sys

import fontspec
import smfont

# Backups live outside the theme. Font::GetFontPaths globs "<name>*" and loads
# every non-.ini hit as a texture page, so "Common default.ini.fontpatch-bak"
# beside the original made RageBitmapTexture fail on launch.
BACKUP_DIR = "fontpatch-backup"
LEGACY_BAK_SUFFIX = ".fontpatch-bak"
MANIFEST = "fontpatch-manifest.json"
PREFIX = "_fontpatch"

ALL_SCRIPTS = ["vietnamese", "thai", "korean", "chinese"]

# Language pages that ship with the game but that some themes never import.
# Simply Love overrides "_16px fonts" with a list that includes CJK but omits
# Thai and Korean, so those titles render blank even though the glyphs are
# sitting in _fallback. Wiring them up costs one import each and adds no files.
# Our own pages are imported after these, so they take precedence.
EXTRA_FONTS = ["_Thai 16px", "_korean 24px", "_japanese 24px", "_chinese 24px"]

DEFAULT_ROOTS = [
    r"C:\Games\ITGmania",
    os.path.expandvars(r"%PROGRAMFILES%\ITGmania"),
    os.path.expandvars(r"%APPDATA%\ITGmania"),
    os.path.expanduser("~/.itgmania"),
    os.path.expanduser("~/Library/Application Support/ITGmania"),
    "/opt/itgmania",
]

FONT_DIRS = [
    r"C:\Windows\Fonts",
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts"),
    "/usr/share/fonts", "/usr/local/share/fonts",
    os.path.expanduser("~/.fonts"), os.path.expanduser("~/.local/share/fonts"),
    "/System/Library/Fonts", "/Library/Fonts", os.path.expanduser("~/Library/Fonts"),
]

# OFL fonts first, so a generated page can be redistributed upstream.
TTF_PREFS = {
    "thai": ["NotoSansThai_Regular.ttf", "NotoSansThai-Regular.ttf",
             "NotoSansThai[wdth,wght].ttf", "Sarabun_Regular.ttf",
             "Niramit_Regular.ttf", "LeelawUI.ttf", "tahoma.ttf"],
    "korean": ["NanumGothic-Regular.ttf", "NanumGothic.ttf",
               "NotoSansKR-Regular.otf", "NotoSansCJKkr-Regular.otf",
               "malgun.ttf"],
    # Simplified-first: Noto Sans SC also covers the Big5 traditional set,
    # whereas a TC font is missing ~1900 simplified-only forms.
    "chinese": ["NotoSansSC_Regular.otf", "NotoSansSC-Regular.otf",
                "NotoSansCJKsc-Regular.otf", "NotoSansSC[wght].ttf",
                "msyh.ttc", "simsun.ttc"],
}
PROBE = {"thai": "\u0e01", "korean": "\ud55c", "chinese": "\u56fd"}


# ---------------------------------------------------------------- discovery
def _installable(root):
    for theme in themes_of(root):
        if not Target(root, theme).error:
            return True
    return False


def root_error(path):
    """Why `path` is not an ITGmania install, or None if it looks like one."""
    if not os.path.exists(path):
        return "does not exist"
    if not os.path.isdir(path):
        return "is not a directory"
    if not os.path.isdir(os.path.join(path, "Themes")):
        return "has no Themes folder - not an ITGmania install"
    return None


def find_roots(explicit):
    """Roots worth acting on. A bare empty Themes/ directory - common in the
    user data dir - is skipped so it cannot make `verify` fail spuriously."""
    if explicit:
        return [os.path.abspath(r) for r in explicit]
    out = []
    for r in DEFAULT_ROOTS:
        if not r or r in out or not os.path.isdir(os.path.join(r, "Themes")):
            continue
        if _installable(r) or load_manifest(r)["entries"]:
            out.append(r)
    return out


def themes_of(root):
    tdir = os.path.join(root, "Themes")
    if not os.path.isdir(tdir):
        return []
    return sorted(n for n in os.listdir(tdir)
                  if os.path.isdir(os.path.join(tdir, n)))


def search_dirs(root, theme):
    d = [os.path.join(root, "Themes", theme, "Fonts")]
    fb = os.path.join(root, "Themes", "_fallback", "Fonts")
    if os.path.normcase(fb) != os.path.normcase(d[0]):
        d.append(fb)
    return [p for p in d if os.path.isdir(p)]


def find_ttf(script, override=None):
    """Locate a source font for `script`, preferring OFL-licensed ones."""
    if override:
        return override if os.path.isfile(override) else None
    for name in TTF_PREFS[script]:
        for d in FONT_DIRS:
            if not d or not os.path.isdir(d):
                continue
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p
            hits = glob.glob(os.path.join(d, "**", name), recursive=True)
            if hits:
                return hits[0]
    return None


def ttf_covers(ttf, script):
    """Render the probe glyph; blank means the font has no coverage."""
    from PIL import Image, ImageDraw, ImageFont
    try:
        f = ImageFont.truetype(ttf, 48)
    except OSError:
        return False
    im = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((40, 110), PROBE[script], font=f,
                            fill=(255, 255, 255, 255), anchor="ls")
    return im.split()[-1].getbbox() is not None


def license_note(ttf):
    """Short licence tag read from the font's own name table.

    Filename is not evidence: the NanumGothic build shipped with Windows is
    named like the OFL release but its name table says "NHN Corporation".
    Requires fontTools; without it we simply say nothing rather than guess.
    """
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return ""
    try:
        n = TTFont(ttf, fontNumber=0, lazy=True)["name"]
    except Exception:
        return ""
    blob = " ".join(filter(None, (n.getDebugName(i) for i in (0, 13, 14)))).lower()
    if "open font license" in blob or "scripts.sil.org/ofl" in blob:
        return " (OFL)"
    if "apache" in blob:
        return " (Apache-2.0)"
    holder = (n.getDebugName(13) or n.getDebugName(8) or "").strip()
    return " (%s)" % holder[:40] if holder else ""


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(65536), b""):
            h.update(b)
    return h.hexdigest()[:16]


def font_name(script):
    return "%s %s" % (PREFIX, script)


# ---------------------------------------------------------------- analysis
def script_chars(script):
    import compose
    import ttfgen
    if script == "vietnamese":
        return list(compose.TARGETS)
    if script == "thai":
        return list(ttfgen.THAI_BLOCK)
    if script == "chinese":
        return list(ttfgen.cjk_set())
    return list(ttfgen.HANGUL)


class Target(object):
    def __init__(self, root, theme):
        self.root, self.theme = root, theme
        self.dirs = search_dirs(root, theme)
        self.error = None
        self.common_default = smfont.resolve("Common default", self.dirs) if self.dirs else None
        self.body = (smfont.resolve("Common Normal", self.dirs) or
                     smfont.resolve("_open sans semibold 24px", self.dirs)) if self.dirs else None
        if not self.dirs:
            self.error = "no Fonts directory"
        elif not self.common_default:
            self.error = "no Common default font"
        elif not self.body:
            self.error = "no body font to composite from"

    @property
    def owns_common_default(self):
        return os.path.normcase(os.path.dirname(self.common_default)) == \
            os.path.normcase(self.dirs[0])

    @property
    def install_dir(self):
        return os.path.dirname(self.common_default)

    def coverage(self):
        return smfont.coverage("Common Normal", self.dirs) if self.body else {}


#: metadata the music wheel actually puts on screen - the title alone is not
#: enough, a missing glyph in the artist line looks just as broken
SONG_FIELDS = ("TITLE", "SUBTITLE", "ARTIST")


def song_metadata(roots, fields=SONG_FIELDS):
    """-> [(field, value, path)] for every song file under the given roots."""
    out = []
    want = tuple("#%s:" % f for f in fields)
    for root in roots:
        for pat in ("*.sm", "*.ssc"):
            for f in glob.glob(os.path.join(root, "Songs", "**", pat), recursive=True):
                try:
                    txt = open(f, "rb").read(4000).decode("utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                for line in txt.splitlines():
                    for pre in want:
                        if line.startswith(pre):
                            v = line[len(pre):].rstrip(";").strip()
                            if v:
                                out.append((pre[1:-1], v, f))
                            break
    return out


# ---------------------------------------------------------------- ini patch
def patch_import(path, add, remove=False):
    """Add/remove `add` on the [main] import= line. Returns True if changed."""
    data = open(path, "rb").read()
    eol = b"\r\n" if b"\r\n" in data else b"\n"
    lines = data.split(eol)
    out, in_main, done, changed = [], False, False, False
    want = add.encode()

    for ln in lines:
        s = ln.strip()
        if s.startswith(b"[") and s.endswith(b"]"):
            if in_main and not done and not remove:
                out.append(b"import=" + want)
                changed, done = True, True
            in_main = (s.lower() == b"[main]")
        if in_main and s.lower().startswith(b"import="):
            parts = [p.strip() for p in s[7:].split(b",") if p.strip()]
            if remove:
                if want in parts:
                    parts = [p for p in parts if p != want]
                    changed = True
            elif want not in parts:
                parts.append(want)
                changed = True
            done = True
            if parts:
                out.append(b"import=" + b",".join(parts))
            continue
        out.append(ln)

    if in_main and not done and not remove:
        out.append(b"import=" + want)
        changed = True
    if changed:
        open(path, "wb").write(eol.join(out))
    return changed


# ---------------------------------------------------------------- manifest
def load_manifest(root):
    p = os.path.join(root, MANIFEST)
    if os.path.isfile(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except ValueError:
            pass
    return {"version": 2, "entries": {}}


def save_manifest(root, m):
    json.dump(m, open(os.path.join(root, MANIFEST), "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)


def backup_path(root, common_default):
    return os.path.join(root, BACKUP_DIR, _rel(root, common_default))


def _rel(root, p):
    try:
        return os.path.relpath(p, root)
    except ValueError:
        return p


# ---------------------------------------------------------------- install
def _build_spec(script, body, opts, log):
    import compose
    import ttfgen
    if script == "vietnamese":
        b = compose.Builder(body)
        spec = b.build_spec()
        spec["missing"] = [(c, m) for c, m in b.missing]
        return spec
    ttf = find_ttf(script, opts.get(script + "_font"))
    if not ttf:
        raise RuntimeError("no %s source font found (pass --%s-font)" % (script, script))
    if not ttf_covers(ttf, script):
        raise RuntimeError("%s has no %s glyphs" % (os.path.basename(ttf), script))
    lbl = "%s%s" % (os.path.basename(ttf), license_note(ttf))
    if script == "thai":
        return ttfgen.build_thai(body, ttf, source_label=lbl, log=log)
    if script == "chinese":
        return ttfgen.build_chinese(body, ttf, source_label=lbl,
                                       oversample=opts.get("chinese_oversample"),
                                       log=log)
    return ttfgen.build_korean(body, ttf, source_label=lbl,
                                  oversample=opts.get("korean_oversample"), log=log)


def _install_one(root, t, manifest, scripts, opts, quiet=False):
    body = smfont.Font(t.body, t.dirs)
    log = (lambda m: None) if quiet else print
    if not quiet:
        print("  %-26s body font: %s" % (t.theme, os.path.basename(t.body)))

    cd = t.common_default
    bak = backup_path(root, cd)
    legacy = cd + LEGACY_BAK_SUFFIX
    if not os.path.exists(bak):
        os.makedirs(os.path.dirname(bak), exist_ok=True)
        # an older install's backup is the pristine copy - keep it, not cd
        src = legacy if os.path.exists(legacy) else cd
        open(bak, "wb").write(open(src, "rb").read())
    if os.path.exists(legacy):
        os.remove(legacy)

    # shipped language pages first, ours after, so ours take precedence
    extras = []
    if not opts.get("no_extra_scripts"):
        have = smfont.coverage("Common Normal", t.dirs)
        for name in EXTRA_FONTS:
            if smfont.resolve(name, t.dirs) is None:
                continue
            cand = smfont.coverage(name, t.dirs, _top=False)
            new = [ch for ch in cand if ch not in have]
            if not new:
                continue
            patch_import(cd, name)
            extras.append((name, len(new)))
            for ch in new:
                have[ch] = name

    generated, failed = {}, {}
    for script in scripts:
        try:
            spec = _build_spec(script, body, opts, log)
        except Exception as e:
            failed[script] = str(e)
            log("      %-11s SKIPPED: %s" % (script, e))
            continue
        name = font_name(script)
        files = fontspec.write(t.install_dir, name, spec)
        patch_import(cd, name)
        generated[script] = {
            "font": name,
            "glyphs": fontspec.glyph_count(spec),
            "source": spec["source"],
            "files": [_rel(root, f) for f in files],
            "sha": {os.path.basename(f): sha(f) for f in files},
            "unbuildable": ["U+%04X" % ord(c) for c, _ in spec.get("missing", [])],
        }
        log("      %-11s %5d glyphs from %s" % (script, fontspec.glyph_count(spec), spec["source"]))
        if spec.get("missing"):
            log("                  %d not buildable from this font: %s"
                % (len(spec["missing"]), " ".join(c for c, _ in spec["missing"])))

    key = os.path.normcase(os.path.relpath(cd, root))
    # Merge rather than replace: installing a subset (--scripts thai) must not
    # drop the record of scripts installed earlier, or uninstall would orphan
    # their files and import lines.
    prev = manifest["entries"].get(key, {})
    all_scripts = dict(prev.get("scripts", {}))
    all_scripts.update(generated)
    manifest["entries"][key] = {
        "theme": t.theme,
        "common_default": _rel(root, cd),
        "backup": _rel(root, bak),
        "body_font": _rel(root, t.body),
        "scripts": all_scripts,
        "failed": failed,
        "extra_imports": sorted(set(prev.get("extra_imports", [])) |
                                {n for n, _ in extras}),
    }
    for name, n in extras:
        log("      wired up %-16s (+%d glyphs already shipped, never imported)" % (name, n))
    return not failed


def cmd_install(args):
    roots = find_roots(args.root)
    if not roots:
        print("No ITGmania install found. Pass --root <path>.")
        return 1
    scripts = [s.strip() for s in (args.scripts or ",".join(ALL_SCRIPTS)).split(",") if s.strip()]
    bad = [s for s in scripts if s not in ALL_SCRIPTS]
    if bad:
        print("unknown script(s): %s  (choose from %s)" % (", ".join(bad), ", ".join(ALL_SCRIPTS)))
        return 1
    opts = {"thai_font": args.thai_font, "korean_font": args.korean_font,
            "chinese_font": args.chinese_font,
            "korean_oversample": args.korean_oversample,
            "chinese_oversample": args.chinese_oversample,
            "no_extra_scripts": args.no_extra_scripts}
    rc = 0
    for root in roots:
        if not _installable(root):
            continue
        print("\n=== %s" % root)
        manifest = load_manifest(root)
        wanted = args.theme or themes_of(root)
        wanted = sorted(set(wanted), key=lambda n: (n != "_fallback", n.lower()))
        seen = set()
        for theme in wanted:
            t = Target(root, theme)
            if t.error:
                if args.theme:
                    print("  %-26s skipped: %s" % (theme, t.error))
                    rc = 1
                continue
            key = os.path.normcase(t.common_default)
            if key in seen:
                print("  %-26s covered by %s" % (theme, _rel(root, t.common_default)))
                continue
            seen.add(key)
            try:
                if not _install_one(root, t, manifest, scripts, opts):
                    rc = 1
            except Exception as e:
                print("  %-26s FAILED: %s" % (theme, e))
                rc = 1
        save_manifest(root, manifest)
        print("\n  manifest: %s" % os.path.join(root, MANIFEST))
    return rc


# ---------------------------------------------------------------- scan
def cmd_scan(args):
    roots = find_roots(args.root)
    if not roots:
        print("No ITGmania install found. Pass --root <path>.")
        return 1
    for root in roots:
        if not _installable(root):
            continue
        print("\n=== %s" % root)
        meta = song_metadata([root])
        for theme in themes_of(root):
            t = Target(root, theme)
            if t.error:
                continue
            cov = t.coverage()
            cols = []
            for s in ALL_SCRIPTS:
                chars = script_chars(s)
                miss = sum(1 for c in chars if c not in cov)
                cols.append("%s %d/%d" % (s[:4], len(chars) - miss, len(chars)))
            broken = [(fld, v, [c for c in v if c not in cov]) for fld, v, _ in meta]
            broken = [b for b in broken if b[2]]
            print("  %-26s %-44s affected %s: %d"
                  % (theme, "  ".join(cols), "/".join(f.lower() for f in SONG_FIELDS),
                     len(broken)))
            if args.verbose:
                for fld, v, bad in broken[:12]:
                    print("        %-9s %-42s missing: %s"
                          % (fld, v[:42], "".join(dict.fromkeys(bad))))
    return 0


# ---------------------------------------------------------------- verify
def cmd_verify(args):
    roots = find_roots(args.root)
    rc = 0
    for root in roots:
        if not _installable(root) and not load_manifest(root)["entries"]:
            continue
        print("\n=== %s" % root)
        manifest = load_manifest(root)
        if not manifest["entries"]:
            print("  nothing installed (run: python fontpatch.py install)")
            rc = 1
            continue
        meta = song_metadata([root])
        for key, e in sorted(manifest["entries"].items()):
            problems = []
            cd = os.path.join(root, e["common_default"])
            if not os.path.isfile(cd):
                problems.append("common default gone")
            else:
                if os.path.isfile(cd + LEGACY_BAK_SUFFIX):
                    problems.append("old backup beside Common default breaks font loading")
                txt = open(cd, "rb").read().decode("utf-8", "replace")
                for s, g in e.get("scripts", {}).items():
                    if g["font"] not in txt:
                        problems.append("%s import lost (theme updated?)" % s)
            for s, g in e.get("scripts", {}).items():
                for rel in g["files"]:
                    if not os.path.isfile(os.path.join(root, rel)):
                        problems.append("%s: missing %s" % (s, os.path.basename(rel)))
            t = Target(root, e["theme"])
            if not t.error:
                cov = t.coverage()
                for s in e.get("scripts", {}):
                    miss = [c for c in script_chars(s) if c not in cov]
                    if miss:
                        problems.append("%s: %d glyph(s) unreachable" % (s, len(miss)))
                stillbad = {c for _, v, _ in meta for c in v if c not in cov}
                if stillbad:
                    problems.append("%d char(s) in your song metadata still uncovered"
                                    % len(stillbad))
            print("  [%s] %-26s %s" % ("OK " if not problems else "BAD", e["theme"],
                                       "; ".join(problems) or "all good"))
            if problems:
                rc = 1
        if rc:
            print("\n  re-run:  python fontpatch.py install")
    return rc


# ---------------------------------------------------------------- uninstall
def cmd_uninstall(args):
    for root in find_roots(args.root):
        manifest = load_manifest(root)
        if not manifest["entries"]:
            continue
        print("\n=== %s" % root)
        for key, e in sorted(manifest["entries"].items()):
            bak = os.path.join(root, e["backup"])
            cd = os.path.join(root, e["common_default"])
            legacy = cd + LEGACY_BAK_SUFFIX
            if not os.path.isfile(bak) and os.path.isfile(legacy):
                bak = legacy
            if os.path.isfile(bak):
                open(cd, "wb").write(open(bak, "rb").read())
                os.remove(bak)
                print("  restored %s" % e["common_default"])
            if os.path.isfile(legacy):
                os.remove(legacy)
            for s, g in e.get("scripts", {}).items():
                for rel in g["files"]:
                    p = os.path.join(root, rel)
                    if os.path.isfile(p):
                        os.remove(p)
                print("  removed  %s (%s)" % (g["font"], s))
        p = os.path.join(root, MANIFEST)
        if os.path.isfile(p):
            os.remove(p)
        # prune now-empty backup directories, deepest first
        for d, _, _ in sorted(os.walk(os.path.join(root, BACKUP_DIR)), reverse=True):
            try:
                os.rmdir(d)
            except OSError:
                pass
    return 0


# ---------------------------------------------------------------- preview
def render(dirs, text, px=34):
    """Render text from the installed files, following Font.cpp: centred
    width cropping, DrawExtraPixels (clamped), and zero-advance overlays."""
    from PIL import Image
    cov = smfont.coverage("Common Normal", dirs)
    cache, glyphs = {}, []
    for ch in text:
        src = cov.get(ch)
        if not src:
            continue
        path, page_name = src
        if path not in cache:
            cache[path] = smfont.Font(path, dirs)
        f = cache[path]
        if ch not in f.chars or page_name not in f.pages:
            continue
        glyphs.append((ch, f, f.pages[page_name]))
    if not glyphs:
        return None

    k = px / 24.0
    maxb = max(p.baseline for _, _, p in glyphs)
    maxd = max(p.src_h - p.baseline for _, _, p in glyphs)
    H = int((maxb + maxd) * k) + int(8 * k)
    adv_total = sum(f.width(ch) + p.adv_extra for ch, f, p in glyphs)
    W = int(adv_total * k) + int(120 * k)
    out = Image.new("RGBA", (max(W, 8), max(H, 8)), (0, 0, 0, 0))

    x = 40.0 * k
    for ch, f, p in glyphs:
        w = f.width(ch)
        eL, eR = p.extra_l + 1, p.extra_r + 1
        if eL % 2:
            eL += 1
        eL = min(eL, (p.src_w - w) / 2.0)
        eR = min(eR, (p.src_w - w) / 2.0)
        chop = p.src_w - w
        # centred crop, then widened by the extra pixels
        left = (chop / 2.0 - eL) * p.scale
        right = p.art_w - (chop / 2.0 - eR) * p.scale
        cell = f.cell(ch)
        piece = cell.crop((int(round(max(0, left))), 0,
                           int(round(min(p.art_w, right))), int(round(p.art_h))))
        tw = max(1, int(round(piece.width / p.scale * k)))
        th = max(1, int(round(piece.height / p.scale * k)))
        piece = piece.resize((tw, th), 1)
        out.alpha_composite(piece, (int(round(x - eL * k)),
                                    int(round((maxb - p.baseline) * k))))
        x += (w + p.adv_extra) * k
    bb = out.split()[-1].getbbox()
    return out.crop((0, 0, min(out.width, (bb[2] + int(20 * k)) if bb else out.width), out.height))


def cmd_preview(args):
    from PIL import Image, ImageDraw, ImageFont
    roots = find_roots(args.root)
    if not roots:
        print("No ITGmania install found.")
        return 1
    root = roots[0]
    theme = (args.theme or ["Simply Love"])[0]
    dirs = search_dirs(root, theme)
    if args.text:
        lines = [args.text]
    else:
        lines = sorted({v for _, v, _ in song_metadata([root])
                        if any(ord(c) > 127 for c in v)})
        lines = lines or ["V\u1ebft X\u01b0\u1edbc"]
    strips = [(s, render(dirs, s)) for s in lines]
    strips = [(s, im) for s, im in strips if im]
    if not strips:
        print("nothing to render")
        return 1
    W = max(im.width for _, im in strips) + 32
    H = sum(im.height + 8 for _, im in strips) + 46
    out = Image.new("RGBA", (W, H), (20, 22, 28, 255))
    d = ImageDraw.Draw(out)
    try:
        lab = ImageFont.truetype("segoeui.ttf", 13)
    except OSError:
        lab = ImageFont.load_default()
    d.text((16, 24), "theme: %s  -  rendered from the installed font files" % theme,
           font=lab, fill=(120, 220, 160, 255), anchor="ls")
    y = 34
    for _, im in strips:
        out.alpha_composite(im, (16, y))
        y += im.height + 8
        d.line([(0, y - 4), (W, y - 4)], fill=(42, 46, 56, 255))
    out.save(args.out)
    print("wrote %s  (%d lines)" % (args.out, len(strips)))
    return 0


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    for name, fn, helptext in (
            ("scan", cmd_scan, "report script coverage per theme"),
            ("install", cmd_install, "generate and wire up the fonts (idempotent)"),
            ("verify", cmd_verify, "check the install is still intact"),
            ("uninstall", cmd_uninstall, "restore every patched file"),
            ("preview", cmd_preview, "render proof from the installed files")):
        p = sub.add_parser(name, help=helptext)
        p.set_defaults(func=fn)
        p.add_argument("--root", action="append", help="ITGmania root (repeatable)")
        p.add_argument("--theme", action="append", help="limit to theme (repeatable)")
        if name == "scan":
            p.add_argument("-v", "--verbose", action="store_true",
                           help="list the affected song titles")
        if name == "install":
            p.add_argument("--scripts", help="comma list: %s" % ",".join(ALL_SCRIPTS))
            p.add_argument("--thai-font", help="path to a Thai TTF")
            p.add_argument("--korean-font", help="path to a Korean TTF")
            p.add_argument("--chinese-font", help="path to a Chinese TTF/OTF")
            p.add_argument("--korean-oversample", type=int, default=None,
                           help="texture scale (default: sharpest that fits 2 pages)")
            p.add_argument("--chinese-oversample", type=int, default=None,
                           help="texture scale (default: sharpest that fits 2 pages)")
            p.add_argument("--no-extra-scripts", action="store_true",
                           help="skip wiring up the shipped Thai/Korean/CJK pages")
        if name == "preview":
            p.add_argument("--text", help="text to render (default: your song titles)")
            p.add_argument("-o", "--out", default="fontpatch-preview.png")
    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 1
    bad = [(r, root_error(r)) for r in (args.root or [])]
    bad = [(r, e) for r, e in bad if e]
    for r, e in bad:
        print("--root %s: %s" % (r, e))
    if bad:
        return 2
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("This tool needs Pillow.\n\n    %s -m pip install Pillow\n"
              % os.path.basename(sys.executable))
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
