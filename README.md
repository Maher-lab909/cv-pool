# The Pool — CV Intake

The first layer of my talent pool: an engine that turns a pile of CVs into clean, searchable text — automatically.

## The pool today
- **372 CVs** in the pool, **100% read** — every one turned into clean text, zero failures.
- Grows continuously from three channels, each tagged automatically by the folder it lands in:
  - **LinkedIn** — CVs candidates send me in DMs
  - **Form** — a Google Form candidates fill in themselves
  - **Network** — people from my real-life recruiting network

## How it reads a CV (cheapest path first)
1. **Normal PDF** → pdfplumber (free, instant)
2. **Scanned / image PDF** → pages rendered to images, read by a vision model
3. **Word (.docx)** → text pulled straight out, with a backup reader for damaged files

Every file is fingerprinted and logged, so re-runs only handle what's new — drop in a new CV and only the new one gets processed.

**Run:** `python intake.py`

## Privacy
CVs and all extracted candidate data stay on my machine and are never committed to this repo (see `.gitignore`). This repo is the engine only.