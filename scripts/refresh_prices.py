"""
refresh_prices.py

Runs daily (via GitHub Actions) to:
  1. Read data/cases.json for case and item contents
  2. Fetch the lowest Steam Community Market price for every item
     across all (available) wear conditions
  3. Calculate a float-weighted average price per item (accounting for
     the probability of each wear dropping)
  4. Apply Steam's 15% market cut (multiply by 0.85)
  5. Write results to data/prices.json

"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

# Paths ─────────────────────────────────────────────────────────────────────

ROOT       = Path(__file__).parent.parent
CASES_PATH = ROOT / "data" / "cases.json"
PRICES_PATH = ROOT / "data" / "prices.json"

# Constants ─────────────────────────────────────────────────────────────────

STEAM_MARKET_URL = "https://steamcommunity.com/market/priceoverview/"
APP_ID           = "730"        # CS2
CURRENCY         = "1"          # USD
STEAM_CUT        = 0.85         # Steam community market cut
REQUEST_DELAY    = 3.0          # seconds between Steam requests

WEAR_THRESHOLDS = [
    ("Factory New",    0.00, 0.07),
    ("Minimal Wear",   0.07, 0.15),
    ("Field-Tested",   0.15, 0.38),
    ("Well-Worn",      0.38, 0.45),
    ("Battle-Scarred", 0.45, 1.00),
]

# Must match rarity strings in cases.json
RARITY_RATES = {
    "Mil-Spec Grade": 0.7992,
    "Restricted":     0.1598,
    "Classified":     0.0320,
    "Covert":         0.0064,
}

# Steam fetching ────────────────────────────────────────────────────────────

def fetch_lowest_price(client: httpx.Client, market_hash_name: str) -> float | None:
    """
    Fetch the lowest listing price for a single item from Steam.
    Returns the price as a float, or None if no listing exists.
    """
    try:
        response = client.get(
            STEAM_MARKET_URL,
            params={
                "appid":            APP_ID,
                "currency":         CURRENCY,
                "market_hash_name": market_hash_name,
            },
            timeout=10,
        )

        if response.status_code == 429:
            print(f"    Rate limited. Waiting 60 seconds...")
            time.sleep(60)
            return fetch_lowest_price(client, market_hash_name)

        if response.status_code != 200:
            print(f"    HTTP {response.status_code} for: {market_hash_name}")
            return None

        data = response.json()

        if not data.get("success"):
            return None

        # Steam returns prices as strings
        price_str = data.get("lowest_price")
        if not price_str:
            return None

        return parse_price(price_str)

    except Exception as e:
        print(f"    Error fetching '{market_hash_name}': {e}")
        return None


def parse_price(price_str: str) -> float:
    """Convert Steam price string '$1,234.56' to float 1234.56"""
    return float(price_str.replace("$", "").replace(",", ""))


# Float / wear probability math ─────────────────────────────────────────────

def compute_wear_probabilities(min_float: float, max_float: float) -> dict[str, float]:
    """
    For each wear condition, compute the probability of a skin dropping
    in that wear given its float range.

    probability = overlap(wear_range, skin_range) / total_skin_range
    """
    total_range = max_float - min_float
    if total_range <= 0:
        return {}

    probabilities = {}
    for wear_name, wear_min, wear_max in WEAR_THRESHOLDS:
        overlap = max(0.0, min(wear_max, max_float) - max(wear_min, min_float))
        if overlap > 0:
            probabilities[wear_name] = overlap / total_range

    return probabilities


# Price computation ─────────────────────────────────────────────────────────

def compute_weighted_price(
    client:       httpx.Client,
    base_name:    str,
    wear_probs:   dict[str, float],
    valid_wears:  list[str],
    stattrak:     bool = False,
) -> float | None:
    """
    Fetch prices for each valid wear of an item, then compute the
    float-probability-weighted average price after Steam's cut.

    Returns None if no valid wear had an active listing.
    """
    prefix = "StatTrak\u2122 " if stattrak else ""
    weighted_sum = 0.0
    total_prob_with_prices = 0.0

    for wear in valid_wears:
        prob = wear_probs.get(wear, 0.0)
        if prob == 0:
            continue

        hash_name = f"{prefix}{base_name} ({wear})"
        print(f"    Fetching: {hash_name}")

        price = fetch_lowest_price(client, hash_name)
        time.sleep(REQUEST_DELAY)

        if price is None:
            print(f"      -> No listing, skipping wear")
            continue

        print(f"      -> ${price:.2f}")
        weighted_sum          += prob * price
        total_prob_with_prices += prob

    if total_prob_with_prices == 0:
        return None

    # Renormalise across wears that actually had listings, then apply Steam cut
    # e.g. some wears have no listings on SM and then probability < 1
    # Need weights to still sum to 1 before applying the cut
    normalised_price = (weighted_sum / total_prob_with_prices) * STEAM_CUT
    return round(normalised_price, 6)


# Main ──────────────────────────────────────────────────────────────────────

def main():
    # Load case definitions
    cases_data = json.loads(CASES_PATH.read_text())
    cases      = cases_data["cases"]
    print(f"Loaded {len(cases)} cases from cases.json\n")

    prices = {}

    with httpx.Client() as client:
        for case in cases:
            case_name = case["name"]
            case_hash = case["market_hash_name"]
            print(f"\n{'='*60}")
            print(f"Case: {case_name}")
            print(f"{'='*60}")

            # Fetch the case price ───────────────────────────────
            print(f"  Fetching case price: {case_hash}")
            case_price = fetch_lowest_price(client, case_hash)
            time.sleep(REQUEST_DELAY)

            if case_price is not None:
                print(f"  Case price: ${case_price:.2f}")
                # Case price is cost
                prices[case_hash] = round(case_price, 6)
            else:
                print(f"  No listing for case, skipping")
                continue

            # Process each item ─────────────────────────────────────────
            for item in case["items"]:
                item_name   = item["name"]
                min_float   = item["min_float"]
                max_float   = item["max_float"]
                valid_wears = item["wears"]
                has_st      = item["stattrak"]

                print(f"\n  Item: {item_name}")

                wear_probs = compute_wear_probabilities(min_float, max_float)

                # Normal version
                normal_price = compute_weighted_price(
                    client, item_name, wear_probs, valid_wears, stattrak=False
                )
                if normal_price is not None:
                    prices[item_name] = normal_price
                    print(f"  -> Normal weighted price (after cut): ${normal_price:.4f}")
                else:
                    print(f"  -> No listings for any wear, skipping item")

                # StatTrak version
                if has_st:
                    st_price = compute_weighted_price(
                        client, item_name, wear_probs, valid_wears, stattrak=True
                    )
                    if st_price is not None:
                        prices[f"StatTrak\u2122 {item_name}"] = st_price
                        print(f"  -> StatTrak weighted price (after cut): ${st_price:.4f}")
                    else:
                        print(f"  -> No StatTrak listings, skipping")

    # Write prices.json ─────────────────────────────────────────────────
    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "prices":       prices,
    }

    PRICES_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRICES_PATH.write_text(json.dumps(output, indent=2))

    print(f"\n{'='*60}")
    print(f"Done. Wrote {len(prices)} price entries to {PRICES_PATH}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()