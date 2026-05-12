"""
merge_prices.py

Combines all partial prices_case_{index}.json files produced by
parallel refresh_prices.py jobs into a single data/prices.json.

"""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT        = Path(__file__).parent.parent
DATA_DIR    = ROOT / "data"
PRICES_PATH = DATA_DIR / "prices.json"


def main():
    partial_files = sorted(DATA_DIR.glob("prices_case_*.json"))

    if not partial_files:
        print("No partial price files found. Nothing to merge.")
        return

    print(f"Found {len(partial_files)} partial files to merge\n")

    merged = {}

    for path in partial_files:
        data = json.loads(path.read_text())
        merged.update(data)
        print(f"  Merged {path.name} ({len(data)} entries)")

    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "prices":       merged,
    }

    PRICES_PATH.write_text(json.dumps(output, indent=2))
    print(f"\nWrote {len(merged)} total entries to prices.json")
    print("\nDone.")


if __name__ == "__main__":
    main()
