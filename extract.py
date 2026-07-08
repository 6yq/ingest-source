#!/usr/bin/env python3
"""extract.py — turn one academic source into plain text with (near) zero model tokens.

The model cannot read PDF/pptx bytes; this does the conversion with local CLIs
(pdftotext, pandoc, curl) + stdlib, and writes clean text you (or a subagent) then
read. Handles: PDF, PPTX, DOCX/ODT/RTF/EPUB/HTML files, a DOI, a URL (PDF or HTML),
or raw text.

Usage:
  extract.py <path>                     # local file, kind by extension
  extract.py 10.1088/1748-0221/…        # DOI  -> Crossref metadata + abstract + refs
  extract.py https://…/paper.pdf        # URL  -> download + pdftotext
  extract.py https://…/page.html        # URL  -> pandoc html->markdown
  extract.py --text "…"  |  --text -    # raw text (─ = stdin)
  [--out DIR] [--title T] [--slug S]

Writes  <out>/<slug>/text.md  and  <out>/<slug>/meta.json,  prints the dir, a
sections outline, and char count so the reader can target sections, not the whole file.
Default out = $MNEME/sources or ./sources.
"""
import sys, os, re, json, subprocess, tempfile, zipfile
import urllib.request, urllib.parse, urllib.error
from pathlib import Path
from xml.etree import ElementTree as ET

def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)

def have(tool):
    return subprocess.run(["command","-v",tool], capture_output=True, shell=False,
                          executable="/bin/bash").returncode == 0 or \
           bool(sh(["bash","-lc",f"command -v {tool}"]).stdout.strip())

def slugify(s, n=60):
    s = re.sub(r"[^\w\s-]", "", (s or "").lower()).strip()
    s = re.sub(r"[\s_-]+", "-", s)
    return (s[:n].strip("-")) or "source"

# ── extractors (each returns markdown text) ─────────────────────────────────
def from_pdf(path):
    r = sh(["pdftotext", "-layout", str(path), "-"])
    if r.returncode != 0 or not r.stdout.strip():
        r = sh(["pdftotext", str(path), "-"])            # fallback: no -layout
    if r.returncode != 0:
        raise RuntimeError("pdftotext failed: " + r.stderr[:200])
    return r.stdout

def from_pptx(path):
    """No libreoffice/python-pptx needed: a .pptx is a zip; pull <a:t> runs per slide."""
    ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    out = []
    with zipfile.ZipFile(path) as z:
        slides = sorted([n for n in z.namelist()
                         if re.match(r"ppt/slides/slide\d+\.xml$", n)],
                        key=lambda n: int(re.search(r"(\d+)", n).group(1)))
        for i, name in enumerate(slides, 1):
            root = ET.fromstring(z.read(name))
            texts = [t.text for t in root.iter(ns + "t") if t.text and t.text.strip()]
            out.append(f"## Slide {i}\n" + "\n".join(texts))
            # speaker notes, if present
            note = f"ppt/notesSlides/notesSlide{i}.xml"
            if note in z.namelist():
                nr = ET.fromstring(z.read(note))
                nt = [t.text for t in nr.iter(ns + "t") if t.text and t.text.strip()]
                if nt: out.append("### Notes\n" + "\n".join(nt))
    return "\n\n".join(out)

def from_pandoc(path, fmt=None):
    cmd = ["pandoc", str(path), "-t", "gfm", "--wrap=none"]
    if fmt: cmd += ["-f", fmt]
    r = sh(cmd)
    if r.returncode != 0:
        raise RuntimeError("pandoc failed: " + r.stderr[:200])
    return r.stdout

def strip_jats(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()

def from_doi(doi):
    doi = re.sub(r"^\s*(doi:|https?://(dx\.)?doi\.org/)", "", doi.strip(), flags=re.I)
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi)
    req = urllib.request.Request(url, headers={"User-Agent": "Mneme-ingest/1 (mailto:local)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        msg = json.load(r)["message"]
    title = " ".join(msg.get("title") or []) or doi
    authors = ", ".join(f"{a.get('given','')} {a.get('family','')}".strip()
                        for a in msg.get("author", []))
    venue = " ".join(msg.get("container-title") or [])
    year = (msg.get("issued", {}).get("date-parts", [[None]])[0] or [None])[0]
    abstract = strip_jats(msg.get("abstract", ""))
    subjects = ", ".join(msg.get("subject", []))
    refs = [strip_jats(" ".join(filter(None, [r.get("article-title"), r.get("journal-title"),
            r.get("year"), r.get("DOI")]))) for r in msg.get("reference", [])][:60]
    body = [f"# {title}", "", f"**Authors:** {authors}", f"**Venue:** {venue} ({year})",
            f"**DOI:** {doi}", f"**Subjects:** {subjects}", "", "## Abstract", abstract or "(no abstract in Crossref)",
            "", "## References", *[f"- {x}" for x in refs if x]]
    return "\n".join(body), {"title": title, "authors": authors, "venue": venue,
                             "year": year, "source": "doi:" + doi}

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mneme-ingest/1"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read(), r.headers.get("Content-Type", "")

def from_url(url):
    data, ctype = fetch(url)
    is_pdf = url.lower().split("?")[0].endswith(".pdf") or "application/pdf" in ctype
    with tempfile.NamedTemporaryFile(suffix=".pdf" if is_pdf else ".html", delete=False) as tf:
        tf.write(data); tmp = tf.name
    try:
        return (from_pdf(tmp) if is_pdf else from_pandoc(tmp, fmt="html")), \
               {"source": url, "title": ""}
    finally:
        try: os.unlink(tmp)
        except OSError: pass

def dispatch(arg, is_text, raw_text):
    if is_text:
        return raw_text, {"source": "text", "title": ""}
    if re.match(r"^https?://", arg):
        return from_url(arg)
    if re.match(r"^(doi:|10\.\d{4,}/)", arg, re.I) or "doi.org/" in arg:
        return from_doi(arg)
    p = Path(arg)
    if not p.exists(): raise SystemExit(f"no such file / not a DOI or URL: {arg}")
    ext = p.suffix.lower()
    if ext == ".pdf":  return from_pdf(p), {"source": p.name, "title": ""}
    if ext == ".pptx": return from_pptx(p), {"source": p.name, "title": ""}
    if ext in (".txt", ".md"): return p.read_text(errors="replace"), {"source": p.name, "title": ""}
    fmtmap = {".odt":"odt",".rtf":"rtf",".epub":"epub",".html":"html",".htm":"html",".docx":"docx"}
    if ext in fmtmap: return from_pandoc(p, fmt=fmtmap[ext]), {"source": p.name, "title": ""}
    if ext == ".ppt":
        raise SystemExit("legacy .ppt unsupported (no libreoffice) — convert to .pptx or .pdf first")
    raise SystemExit(f"unknown extension {ext}; supported: pdf pptx docx odt rtf epub html txt md, or a DOI/URL")

def main():
    a = sys.argv[1:]
    out = None; title = None; slug = None; is_text = False; raw = None; arg = None
    while a:
        x = a.pop(0)
        if x == "--out": out = a.pop(0)
        elif x == "--title": title = a.pop(0)
        elif x == "--slug": slug = a.pop(0)
        elif x == "--text": is_text = True; raw = (sys.stdin.read() if a and a[0]=="-" else (a.pop(0) if a else ""))
        else: arg = x
    if not is_text and not arg: raise SystemExit(__doc__)

    try:
        text, meta = dispatch(arg, is_text, raw)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"fetch failed: HTTP {e.code} for {arg} (bad DOI/URL, or paywalled — "
                         f"try the PDF directly, or paste the text with --text)")
    except (urllib.error.URLError, TimeoutError) as e:
        raise SystemExit(f"network error for {arg}: {e} (offline? use --text, or the WebFetch tool)")
    except RuntimeError as e:
        raise SystemExit(str(e))
    if title: meta["title"] = title
    text = text.replace("\r\n", "\n").strip() + "\n"

    base = out or os.environ.get("MNEME") and (Path(os.environ["MNEME"]) / "sources") or "sources"
    slug = slug or slugify(meta.get("title") or (arg if not is_text else "pasted-text"))
    d = Path(base) / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "text.md").write_text(text, encoding="utf-8")
    meta.update({"chars": len(text), "slug": slug})

    # Keep the original source file WITH its extract, inside the gitignored sources/ tree —
    # never leave a PDF/pptx loose in the repo where it could get committed. If the file is
    # already inside $MNEME (e.g. dropped in the repo root), MOVE it out of the tracked tree;
    # if it lives elsewhere (~/papers/…), COPY it so the user's original stays put.
    if not is_text and arg and Path(arg).is_file():
        import shutil
        srcf = Path(arg).resolve(); dst = (d / srcf.name).resolve()
        mneme_root = Path(base).resolve().parent
        if srcf != dst:
            inside = str(srcf).startswith(str(mneme_root) + os.sep)
            try:
                (shutil.move if inside else shutil.copy2)(str(srcf), str(dst))
                meta["kept_source"] = dst.name
            except OSError:
                pass

    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    # outline = markdown headers, so the reader targets sections not the whole file
    heads = [l for l in text.splitlines() if re.match(r"^#{1,3}\s+\S", l)][:40]
    print(f"OK  {d/'text.md'}  ({len(text)} chars)")
    if meta.get("title"): print("title:", meta["title"])
    print("source:", meta.get("source"))
    print("outline:")
    for h in heads: print("  " + h)
    if not heads: print("  (no headers — flat text; read the head + skim)")

if __name__ == "__main__":
    main()
