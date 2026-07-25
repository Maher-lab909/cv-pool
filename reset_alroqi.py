"""One-off: reset Al-Roqi so build_profiles.py re-profiles just him (dropped dates)."""
import csv
from pathlib import Path

SF = "linkedin__2026 jan - 2026 jul__AbdullahAhmedAlroqi.txt"

# delete his profile
Path("profiles", SF.replace(".txt", ".json")).unlink(missing_ok=True)

# drop his row from the ledger
led = Path("profiles_ledger.csv")
rows = list(csv.DictReader(led.open(encoding="utf-8-sig")))
kept = [r for r in rows if r["source_file"] != SF]
with led.open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys())
    w.writeheader()
    w.writerows(kept)

print(f"Reset Al-Roqi. Ledger {len(rows)} -> {len(kept)} rows.")
print("Now run:  python build_profiles.py   (should say 'to do now: 1')")
