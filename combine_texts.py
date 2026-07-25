"""Combine every extracted CV text into one file, with clear separators."""

from pathlib import Path

BASE = Path(__file__).parent
EXTRACTED = BASE / "extracted"
OUT = BASE / "all_cv_texts.txt"          # gitignored? see note below

files = sorted(p for p in EXTRACTED.glob("*.txt") if p.stat().st_size > 0)

parts = []
for i, p in enumerate(files, start=1):
    text = p.read_text(encoding="utf-8").strip()
    parts.append(
        f"\n{'=' * 78}\n"
        f"### [{i}/{len(files)}] {p.stem}\n"
        f"### chars: {len(text)}\n"
        f"{'=' * 78}\n\n"
        f"{text}\n"
    )

OUT.write_text("".join(parts), encoding="utf-8")
total = sum(len(p.read_text(encoding='utf-8')) for p in files)
print(f"Combined {len(files)} CVs into {OUT.name}  ({total:,} chars, {OUT.stat().st_size/1024/1024:.1f} MB)")