"""Import food products from Open Food Facts.

Two modes:
  API mode  (default) — queries the OFF Search API, no file download needed.
  CSV mode  (--csv)   — parses the full OFF CSV dump you already downloaded.
                        Download: https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz

Usage:
    # API mode — fetch up to 500 products per category for Russia
    python database/import_openfoodfacts.py

    # CSV mode — parse a local dump (handles .gz and plain .csv)
    python database/import_openfoodfacts.py --csv /path/to/openfoodfacts.csv.gz

    # Preview without writing to DB
    python database/import_openfoodfacts.py --dry-run
    python database/import_openfoodfacts.py --csv /path/to/file.csv.gz --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import io
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
import httpx
from sqlalchemy import select

# ── bootstrap: path + env vars ───────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from database.engine import AsyncSessionLocal, init_db
from database.models import FoodProduct

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── OFF Search API ────────────────────────────────────────────────────────────

OFF_API = "https://world.openfoodfacts.org/cgi/search.pl"
OFF_FIELDS = "product_name,product_name_ru,nutriments,completeness"
PAGES_PER_CATEGORY = 5   # 5 × 100 = 500 products per category max
PAGE_SIZE = 100
RATE_LIMIT_DELAY = 1.0   # seconds between API requests (be a good citizen)

# Categories to query.  OFF category tag → human label (for logging).
CATEGORIES: list[tuple[str, str]] = [
    ("en:meats-and-their-products",      "мясо"),
    ("en:fish-and-seafood",              "рыба и морепродукты"),
    ("en:dairy-products",                "молочные"),
    ("en:eggs-and-their-products",       "яйца"),
    ("en:cereals-and-their-products",    "крупы и злаки"),
    ("en:legumes-and-their-products",    "бобовые"),
    ("en:vegetables",                    "овощи"),
    ("en:fruits",                        "фрукты"),
    ("en:nuts",                          "орехи"),
    ("en:fats-and-oils",                 "масла и жиры"),
    ("en:bread-and-similar-products",    "хлеб"),
    ("en:fermented-foods",               "кисломолочные"),
]

# ── Quality filters ───────────────────────────────────────────────────────────

MIN_COMPLETENESS = 0.4   # OFF completeness score 0-1
MAX_CALORIES_100G = 900  # kcal — discard obvious errors
MIN_CALORIES_100G = 1    # kcal — skip water / spices with no value


def _extract_nutriments(p: dict) -> tuple[float, float, float, float] | None:
    """Pull (calories, protein, fat, carbs) per 100g from an OFF product dict.

    Returns None if any value is missing or out of plausible range.
    """
    n = p.get("nutriments", {})

    def _get(key: str) -> float | None:
        v = n.get(key) or n.get(f"{key}_100g")
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    cal   = _get("energy-kcal_100g") or _get("energy-kcal")
    prot  = _get("proteins_100g")    or _get("proteins")
    fat   = _get("fat_100g")         or _get("fat")
    carbs = _get("carbohydrates_100g") or _get("carbohydrates")

    if any(v is None for v in (cal, prot, fat, carbs)):
        return None
    if not (MIN_CALORIES_100G <= cal <= MAX_CALORIES_100G):
        return None
    if any(v < 0 for v in (prot, fat, carbs)):
        return None

    return round(cal, 1), round(prot, 1), round(fat, 1), round(carbs, 1)


def _best_name(p: dict) -> str | None:
    """Return the best available name: prefer Russian, fall back to English."""
    name = (p.get("product_name_ru") or p.get("product_name") or "").strip()
    # Skip very short names, numbers, or brand-code-only entries
    if len(name) < 3 or name.isdigit():
        return None
    return name


# ── API mode ──────────────────────────────────────────────────────────────────

async def _fetch_page(
    client: httpx.AsyncClient,
    category: str,
    page: int,
) -> list[dict]:
    """Fetch one page of OFF products for a category, filtered by Russia."""
    params = {
        "action":         "process",
        "json":           "1",
        "page_size":      PAGE_SIZE,
        "page":           page,
        "sort_by":        "completeness",
        "fields":         OFF_FIELDS,
        "tagtype_0":      "categories",
        "tag_contains_0": "contains",
        "tag_0":          category,
        "tagtype_1":      "countries",
        "tag_contains_1": "contains",
        "tag_1":          "en:russia",
    }
    for attempt in range(3):
        try:
            r = await client.get(OFF_API, params=params, timeout=30)
            r.raise_for_status()
            return r.json().get("products", [])
        except Exception as exc:
            wait = 3 * (2 ** attempt)   # 3s → 6s → 12s
            if attempt < 2:
                logger.warning(
                    "OFF API error (cat=%s page=%d, attempt %d/3), retrying in %ds: %s",
                    category, page, attempt + 1, wait, exc,
                )
                await asyncio.sleep(wait)
            else:
                logger.warning("OFF API failed (cat=%s page=%d): %s", category, page, exc)
    return []


async def collect_from_api() -> list[tuple[str, float, float, float, float]]:
    """Fetch products from OFF API across all categories. Returns (name, cal, prot, fat, carbs)."""
    results: list[tuple[str, float, float, float, float]] = []
    seen_names: set[str] = set()

    headers = {"User-Agent": "FitAgent/1.0 (fitness app; contact: admin@fitagent.app)"}

    async with httpx.AsyncClient(headers=headers) as client:
        for category_tag, category_label in CATEGORIES:
            logger.info("Fetching category: %s …", category_label)
            cat_added = 0

            for page in range(1, PAGES_PER_CATEGORY + 1):
                products = await _fetch_page(client, category_tag, page)
                if not products:
                    break

                for p in products:
                    completeness = float(p.get("completeness") or 0)
                    if completeness < MIN_COMPLETENESS:
                        continue

                    name = _best_name(p)
                    if not name or name.lower() in seen_names:
                        continue

                    macros = _extract_nutriments(p)
                    if macros is None:
                        continue

                    seen_names.add(name.lower())
                    results.append((name, *macros))
                    cat_added += 1

                # Polite rate-limiting
                await asyncio.sleep(RATE_LIMIT_DELAY)

            logger.info("  → %d products added from '%s'", cat_added, category_label)

    return results


# ── CSV mode ──────────────────────────────────────────────────────────────────

# Columns we need from the OFF CSV dump.
CSV_COLS = {
    "product_name_ru", "product_name",
    "energy-kcal_100g",
    "proteins_100g", "fat_100g", "carbohydrates_100g",
    "countries_tags", "completeness",
}


def collect_from_csv(path: str) -> list[tuple[str, float, float, float, float]]:
    """Parse the OFF CSV dump (plain or .gz). Filters for Russian products."""
    results: list[tuple[str, float, float, float, float]] = []
    seen_names: set[str] = set()

    opener = gzip.open if path.endswith(".gz") else open
    logger.info("Reading CSV: %s (this may take a while for the full dump) …", path)

    rows_read = 0
    with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            rows_read += 1
            if rows_read % 100_000 == 0:
                logger.info("  %d rows read, %d products collected …", rows_read, len(results))

            # Country filter
            countries = (row.get("countries_tags") or "").lower()
            if "en:russia" not in countries and "en:kazakhstan" not in countries:
                continue

            # Completeness
            try:
                if float(row.get("completeness") or 0) < MIN_COMPLETENESS:
                    continue
            except ValueError:
                continue

            # Name
            name = (row.get("product_name_ru") or row.get("product_name") or "").strip()
            if not name or len(name) < 3 or name.lower() in seen_names:
                continue

            # Macros
            def _f(col: str) -> float | None:
                try:
                    v = float(row.get(col) or "")
                    return v if v >= 0 else None
                except ValueError:
                    return None

            cal   = _f("energy-kcal_100g")
            prot  = _f("proteins_100g")
            fat   = _f("fat_100g")
            carbs = _f("carbohydrates_100g")

            if any(v is None for v in (cal, prot, fat, carbs)):
                continue
            if not (MIN_CALORIES_100G <= cal <= MAX_CALORIES_100G):
                continue

            seen_names.add(name.lower())
            results.append((name, round(cal, 1), round(prot, 1), round(fat, 1), round(carbs, 1)))

    logger.info("CSV scan complete: %d rows, %d products collected.", rows_read, len(results))
    return results


# ── DB insert ─────────────────────────────────────────────────────────────────

def _print_products(products: list[tuple[str, float, float, float, float]]) -> None:
    print(f"\n{'Название':<40} {'кк':>6}  {'Б':>5}  {'Ж':>5}  {'У':>5}")
    print("-" * 68)
    for name, cal, prot, fat, carbs in products:
        print(f"  {name:<38} {cal:6.1f}  {prot:5.1f}  {fat:5.1f}  {carbs:5.1f}")


async def insert_products(
    products: list[tuple[str, float, float, float, float]],
    dry_run: bool = False,
) -> None:
    """Insert products into food_products, skipping names that already exist."""
    if not products:
        logger.info("Nothing to insert.")
        return

    if dry_run:
        seen: set[str] = set()
        unique = []
        for row in products:
            if row[0].lower() not in seen:
                seen.add(row[0].lower())
                unique.append(row)
        print(f"\nDRY-RUN — {len(unique)} unique products collected:\n")
        _print_products(unique[:40])
        if len(unique) > 40:
            print(f"\n  … and {len(unique) - 40} more")
        return

    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(FoodProduct.name))
        existing_names = {row[0].lower() for row in existing}
        logger.info("Existing DB products: %d", len(existing_names))

        new_items = [
            FoodProduct(name=name, calories=cal, protein=prot, fat=fat, carbs=carbs)
            for name, cal, prot, fat, carbs in products
            if name.lower() not in existing_names
        ]
        logger.info("New unique products to insert: %d", len(new_items))

        if new_items:
            session.add_all(new_items)
            await session.commit()
            logger.info("✓ Inserted %d new products.", len(new_items))
        else:
            logger.info("All products already in DB — nothing inserted.")


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="Import from Open Food Facts")
    parser.add_argument(
        "--csv",
        metavar="PATH",
        help="Path to OFF CSV dump (.csv or .csv.gz). "
             "If omitted, the API is used instead.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print products without writing to DB.",
    )
    args = parser.parse_args()

    if not args.dry_run:
        await init_db()

    if args.csv:
        products = collect_from_csv(args.csv)
    else:
        products = await collect_from_api()

    logger.info("Total candidates after filtering: %d", len(products))
    await insert_products(products, dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
