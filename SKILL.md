---
name: ingest-source
description: Use when the user wants to import EXTERNAL academic material into the palace knowledge graph — a paper, PDF, slide deck (PDF/PPTX), DOI, arXiv id, a URL to any of those, or pasted text ("ingest this paper", "add this PDF/deck to the palace", "read this DOI into my notes", "import this reference", "distill this paper"). Extracts the text with local CLIs (near-zero model tokens), understands it, and writes linked "dots" marked as imported (scope `Lit:<Topic>`, a `source:` field) so outside knowledge is visually separate from your own work. Sibling of `distill-session`, which stays for your OWN Claude Code sessions; this one is for OTHERS' material.
---

# Ingest Source — outside material into palace dots

## What this is

`distill-session` captures what *you* did in a session. **This skill captures what
you *read*** — a paper, deck, DOI, or URL — and files it in the same palace graph, but
clearly marked as **imported** so you can always tell your own findings from the
literature. Same dot schema, same narrative-spine and linking discipline (read the
`distill-session` SKILL.md for those — do not duplicate them here); the differences are
only: how the text gets in (extraction, not a session), and how it is marked (external).

## The pipeline (extract → understand → affiliate → write)

### 1. Extract — spend ~no model tokens on bytes

The model can't read PDF/pptx bytes. Convert first with the bundled dispatcher, which
uses `pdftotext` / `pandoc` / `curl` / stdlib (pptx = a zip of XML, parsed directly):

```bash
export PALACE=~/.claude/palace   # so output lands in $PALACE/sources (gitignored)
~/.claude/skills/ingest-source/extract.py <input> [--slug NAME] [--title T]
```

`<input>` is a file path (`.pdf .pptx .docx .odt .rtf .epub .html .txt .md`), a **DOI**
(`10.xxxx/…` → Crossref metadata + abstract + references, no PDF needed), an **arXiv/URL**
(PDF → `pdftotext`; HTML → pandoc), or `--text "…"` / `--text -` for pasted content.
It writes `$PALACE/sources/<slug>/text.md` + `meta.json` and prints a **header outline**.
Legacy `.ppt` isn't supported (no libreoffice) — ask for a `.pptx` or `.pdf`.

### 2. Understand — outline first, sections next, delegate the read

Minimise tokens: **do not read the whole `text.md` into the main context.** Delegate to
an Explore/general subagent that reads `text.md` and returns only the distilled result —
the same rule `distill-session` uses for long sessions. Point it at the sections that
carry ideas: **abstract → intro/motivation → key results (numbers, figures) → method →
conclusion**; skim the rest. For a DOI-only ingest the abstract + references are often
enough for 1–2 dots. A paper is usually **2–5 dots**, not one dump (Zettelkasten atomicity).

### 3. Affiliate — find the lane and the neighbours by keywords

Extract salient keywords while reading (see the keyword guidance in `distill-session`),
then find where the dot belongs and what it should link to:

```bash
~/.claude/skills/distill-session/affiliate.py --keywords "k1, k2, k3" --title "…"
```

It ranks existing project lanes by keyword overlap and lists candidate `related` dot ids.
Use it to (a) choose the **topic** subject and (b) wire `related`/`informs`/`supports`/
`refutes` edges to your own dots the paper speaks to. This is the whole point — an
imported dot that doesn't touch your work is nearly worthless.

### 4. Write — same schema, marked as imported

Write each dot to `$PALACE/dots/<id>.md` with the `distill-session` schema, plus:

- **`project: Lit:<Topic>`** — the `Lit:` scope puts imported material in its own lane/
  colour. Reuse the subject the affiliate matched (`Lit:Calib`, `Lit:Reco`, `Lit:FSMP`,
  `Lit:Sim`, `Lit:Systematics`, `Lit:Fitters`, …). Keep subjects consistent, like any lane.
- **`source:`** — provenance: the DOI / arXiv id / URL / short cite key (`Author2021`).
  This is what flags the dot as imported; the viewer renders `source:` dots **hollow**
  (vs solid = your work) and offers a *mine / imported* filter. Never leave it blank on
  an imported dot.
- **`id`** — `YYYYMMDD-slug` using the paper's **publication date** (from `meta.json` /
  Crossref), not today's, so it sits at the right point on the roadmap.
- **`## Links`** — `related`/`informs`/`supports`/`refutes` edges to your own dots (from
  the affiliate step) + a `next` spine among the paper's own dots if it has several.

Then reindex + commit, exactly as `distill-session` step 5.

## Dot content, honestly

- Capture the paper's **claim + evidence**, in its authors' voice, not yours. A `result`
  dot records *their* number; an `insight` dot records what it changes for *your* work.
- Keep the author's hedges. Don't inflate a preprint into settled fact.
- Real identifiers: DOI, arXiv id, figure/table numbers, the reported values. No invented
  numbers — if the abstract-only ingest lacks them, say so and keep the dot light.
- One `source:` per dot; if a dot fuses two papers, it's two dots or a synthesis dot that
  links both.

## Red flags — you're doing it wrong if

- You read the raw PDF/`text.md` into the main context instead of `extract.py` + a subagent.
- An imported dot has no `source:` or lives in an experiment lane (`JUNO:*`) instead of `Lit:*`.
- The paper's dots are an island — no `related`/`informs` edge into your own work.
- You invented numbers the extracted text doesn't contain, or dropped the authors' caveats.
- You used it for your OWN session work — that's `distill-session`.
