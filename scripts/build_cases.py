"""
build_cases.py

One-time script (re-run when a new case releases) that:
  1. Fetches case and skin data from the ByMykel CSGO API
  2. Filters to weapon cases only
  3. Cross-references float ranges and StatTrak eligibility from skins.json
  4. Computes valid wear conditions per item using float overlap math
  5. Writes data/cases.json

Run from the project root:
    python scripts/build_cases.py
"""

import json
import httpx
from pathlib import Path

# ── Wear thresholds (fixed by the game) ──────────────────────────────────────

WEAR_THRESHOLDS = [
    ("Factory New",    0.00, 0.07),
    ("Minimal Wear",   0.07, 0.15),
    ("Field-Tested",   0.15, 0.38),
    ("Well-Worn",      0.38, 0.45),
    ("Battle-Scarred", 0.45, 1.00),
]

# ── ByMykel API endpoints ─────────────────────────────────────────────────────

BASE_URL   = "https://raw.githubusercontent.com/ByMykel/CSGO-API/main/public/api/en"
CRATES_URL = f"{BASE_URL}/crates.json"
SKINS_URL  = f"{BASE_URL}/skins.json"

# ── Output path ───────────────────────────────────────────────────────────────

OUTPUT_PATH = Path(__file__).parent.parent / "data" / "cases.json"


def fetch_json(url: str) -> list | dict:
    print(f"Fetching {url} ...")
    response = httpx.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def compute_valid_wears(min_float: float, max_float: float) -> list[str]:
    """
    Return wear condition names where the skin's float range overlaps
    with that wear's threshold range.

    Overlap = max(0, min(wear_max, skin_max) - max(wear_min, skin_min))
    """
    valid = []
    for wear_name, wear_min, wear_max in WEAR_THRESHOLDS:
        overlap = max(0.0, min(wear_max, max_float) - max(wear_min, min_float))
        if overlap > 0:
            valid.append(wear_name)
    return valid


def build_skin_lookup(skins: list) -> dict:
    """
    Build a dict keyed by base skin name (e.g. "AK-47 | Redline") containing
    float range and StatTrak eligibility.

    ByMykel skin names include the pattern name only, not wear — so they match
    the base names we get from crates.json contains[].name.
    """
    lookup = {}
    for skin in skins:
        name = skin.get("name")
        if not name:
            continue
        lookup[name] = {
            "min_float": skin.get("min_float", 0.00),
            "max_float": skin.get("max_float", 1.00),
            "stattrak":  skin.get("stattrak", False),
        }
    return lookup


def build_cases(crates: list, skin_lookup: dict) -> list:
    cases = []

    for crate in crates:
        # Filter to weapon cases only
        if crate.get("type") != "Case":
            continue

        case_id   = crate["id"]
        case_name = crate["name"]
        case_hash = crate["market_hash_name"]
        contains  = crate.get("contains", [])

        # Skip cases with no items (e.g. very old cases with no market data)
        if not contains:
            print(f"  Skipping {case_name} — no items in contains[]")
            continue

        items = []
        for item in contains:
            item_name = item.get("name")
            rarity    = item.get("rarity", {}).get("name", "Unknown")

            if not item_name:
                continue

            # Cross-reference skins.json for float data and StatTrak
            skin_data = skin_lookup.get(item_name)
            if skin_data:
                min_float = skin_data["min_float"]
                max_float = skin_data["max_float"]
                stattrak  = skin_data["stattrak"]
            else:
                # Fallback: assume full float range, no StatTrak
                # This shouldn't happen often but handles edge cases
                print(f"    Warning: '{item_name}' not found in skins.json, using defaults")
                min_float = 0.00
                max_float = 1.00
                stattrak  = False

            valid_wears = compute_valid_wears(min_float, max_float)

            items.append({
                "name":       item_name,
                "rarity":     rarity,
                "min_float":  min_float,
                "max_float":  max_float,
                "stattrak":   stattrak,
                "wears":      valid_wears,
            })

        if not items:
            print(f"  Skipping {case_name} — no valid items after processing")
            continue

        print(f"  Built {case_name} ({len(items)} items)")
        cases.append({
            "id":               case_id,
            "name":             case_name,
            "market_hash_name": case_hash,
            "items":            items,
        })

    return cases


def main():
    crates = fetch_json(CRATES_URL)
    skins  = fetch_json(SKINS_URL)

    print(f"\nLoaded {len(crates)} crates and {len(skins)} skins\n")

    skin_lookup = build_skin_lookup(skins)
    cases       = build_cases(crates, skin_lookup)

    output = {"cases": cases}

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print(f"\nDone. Wrote {len(cases)} cases to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()