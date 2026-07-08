# The Pool — CV Intake

The first layer of my talent pool: turns a folder of CVs into clean, searchable text.

Reads three ways, cheapest first — pdfplumber for normal PDFs, a vision model for scanned ones, a direct reader for Word files. Every file is fingerprinted and logged, so re-runs only handle what's new.

**Coverage:** 372 / 372 CVs read (100%) · **Run:** `python intake.py`

CVs and extracted data stay on my machine and are never committed (see `.gitignore`).