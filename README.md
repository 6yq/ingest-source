# ingest-source

A Claude Code **skill** that imports *external* academic material — a paper, PDF,
slide deck (PDF/PPTX), DOI, arXiv id, a URL to any of those, or pasted text — into a
[palace](https://github.com/6yq/palace) knowledge graph as linked markdown **dots**,
clearly marked as *imported* (their own `Lit:<Topic>` lane + a `source:` field) so
outside knowledge stays visually distinct from your own work.

Sibling of [distill-session](https://github.com/6yq/distill-session): that one captures
*your* Claude Code sessions; this one captures what you *read*.

## How it works

1. **`extract.py`** turns the source into plain text with local CLIs — `pdftotext`,
   `pandoc`, `curl`, and stdlib (a `.pptx` is a zip of XML, parsed directly; a DOI is
   resolved via the Crossref API). The model spends ~no tokens on the bytes.
2. A subagent reads the extracted text (outline first) and distils it into dots.
3. **`affiliate.py`** (from `distill-session`) places each dot by keyword overlap and
   suggests which of your own dots it should link to.

See `SKILL.md` for the full workflow.

## Requires

`pdftotext` (poppler), `pandoc`, `curl`, `python3` (stdlib only). Legacy `.ppt` needs
LibreOffice; convert to `.pptx`/`.pdf` first.
