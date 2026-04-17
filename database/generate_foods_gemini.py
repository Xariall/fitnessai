"""Generate food products via Gemini and insert into the DB.

Queries Gemini in batches — one request per food category.
Each batch returns ~20 products with nutritional data per 100g.
Deduplicates against the existing DB before inserting.

Usage:
    python database/generate_foods_gemini.py

    # Preview first 20 items per category without writing
    python database/generate_foods_gemini.py --dry-run

    # Only specific categories (comma-separated indices from the list below)
    python database/generate_foods_gemini.py --categories 0,1,2

Requires: GEMINI_API_KEY in environment (or .env file).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
import google.genai as genai_sdk
from google.genai import types as genai_types
from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from database.engine import AsyncSessionLocal, init_db
from database.models import FoodProduct

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Food categories ───────────────────────────────────────────────────────────
# Each entry: (category_name, count_to_generate, extra_context)

CATEGORIES: list[tuple[str, int, str]] = [
    # (label, n_products, extra hint for Gemini)
    ("Мясо и птица (сырое)",          25, "говядина, свинина, баранина, курица, индейка, утка, кролик, телятина, конина — разные части"),
    ("Рыба (сырая)",                   25, "лосось, тунец, треска, минтай, скумбрия, сёмга, судак, карп, форель, горбуша, сельдь, окунь — разные виды"),
    ("Морепродукты",                   15, "креветки, кальмар, мидии, краб, осьминог, гребешок — варёные и сырые"),
    ("Молочные продукты",              25, "молоко, кефир, ряженка, творог разной жирности, сметана, сливки, масло, йогурт без добавок — разная жирность"),
    ("Сыры",                           15, "твёрдые, мягкие, плавленые, рассольные — российские и популярные импортные"),
    ("Яйца",                           5,  "куриное, перепелиное, утиное — разные способы приготовления"),
    ("Крупы и злаки (сухие)",          20, "рис, гречка, овсянка, пшено, перловка, булгур, кускус, полба, манка, кукурузная крупа"),
    ("Макаронные изделия",             8,  "спагетти, пенне, гречневая лапша, рисовая лапша — сухие"),
    ("Бобовые (сухие и варёные)",      12, "чечевица, нут, фасоль, горох, соя, маш — сухие и варёные"),
    ("Хлеб и выпечка",                 15, "белый, чёрный, ржаной, цельнозерновой, лаваш, питта, багет, хлебцы"),
    ("Овощи свежие",                   30, "все популярные в России — помидор, огурец, перец, кабачок, баклажан, капуста, морковь, свёкла, лук, чеснок, шпинат, брокколи, тыква, картофель, батат"),
    ("Грибы",                          10, "шампиньон, вешенка, белый, подосиновик — свежие и сушёные"),
    ("Фрукты свежие",                  20, "яблоко, груша, банан, апельсин, мандарин, лимон, персик, абрикос, слива, вишня, черешня, виноград, киви, манго"),
    ("Ягоды",                          12, "клубника, малина, черника, голубика, смородина, ежевика, клюква, брусника"),
    ("Орехи и семена",                 15, "миндаль, грецкий, кешью, фундук, арахис, фисташки, семена льна, тыквы, кунжут, подсолнечника"),
    ("Масла растительные",             8,  "подсолнечное, оливковое, кукурузное, кокосовое, льняное, кунжутное"),
    ("Сухофрукты",                     10, "изюм, чернослив, курага, финики, инжир, клюква сушёная"),
    ("Готовые блюда (русская кухня)",  20, "борщ, щи, рассольник, солянка, гречка с курицей, плов, пельмени, вареники, котлеты, запечённая рыба, омлет — конкретные блюда с типичным рецептом"),
    ("Молочные каши",                  8,  "овсяная, гречневая, рисовая, пшённая каша на молоке — стандартный рецепт"),
    ("Спортивное и специальное питание", 10, "протеиновый порошок (whey/casein), гейнер, протеиновый батончик, BCAA (не считать), рыбий жир"),
    ("Колбасные изделия и мясные деликатесы", 15, "варёная колбаса, сосиски, сардельки, ветчина, буженина, карбонад, паштет — типичные российские"),
    ("Консервы",                       10, "тунец в собственном соку, сардины в масле, горошек, кукуруза, фасоль, томаты"),
    ("Приправы, соусы (с ненулевым КБЖУ)", 8, "майонез, сметанный соус, горчица, кетчуп — только те, у которых есть значимые калории"),
]

# ── Prompt building ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "Ты эксперт-нутрициолог. Твоя задача — предоставить точные данные о питательной ценности продуктов.\n"
    "Используй официальные таблицы (Скурихин, USDA) как источник. Данные — на 100г продукта.\n"
    "Отвечай ТОЛЬКО валидным JSON-массивом без markdown, пояснений и лишних символов."
)


def _build_prompt(category: str, count: int, hint: str) -> str:
    return (
        f"Дай список из {count} продуктов в категории «{category}».\n"
        f"Уточнение: {hint}\n\n"
        "Каждый элемент массива — объект:\n"
        '{"name": "название на русском", "calories": число, "protein": число, "fat": число, "carbs": число}\n\n'
        "Требования:\n"
        "- calories, protein, fat, carbs — числа (float) на 100г\n"
        "- name — чёткое российское название продукта, без бренда\n"
        "- Не дублируй продукты внутри ответа\n"
        "- Не добавляй продукты из других категорий\n"
        f"- Верни ровно {count} объектов"
    )


# ── Gemini call ───────────────────────────────────────────────────────────────

async def _generate_category(
    client: genai_sdk.Client,
    category: str,
    count: int,
    hint: str,
) -> list[tuple[str, float, float, float, float]]:
    """Generate nutritional data for one food category. Returns validated rows."""
    prompt = _build_prompt(category, count, hint)
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    # Retry with exponential backoff — handles 503 load spikes
    response = None
    for attempt in range(3):
        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=f"{SYSTEM_PROMPT}\n\n{prompt}",
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            break
        except Exception as exc:
            wait = 3 * (2 ** attempt)   # 3s → 6s → 12s
            if attempt < 2:
                logger.warning(
                    "Gemini '%s' attempt %d/3 failed, retrying in %ds: %s",
                    category, attempt + 1, wait, exc,
                )
                await asyncio.sleep(wait)
            else:
                logger.error("Gemini '%s' failed after 3 attempts: %s", category, exc)
                return []

    if response is None:
        return []

    raw = re.sub(r"```json\s*|```", "", response.text).strip()
    try:
        items = json.loads(raw)
        if not isinstance(items, list):
            raise ValueError("Expected JSON array")
    except Exception as exc:
        logger.warning("JSON parse error for '%s': %s\nRaw: %s", category, exc, raw[:200])
        return []

    results: list[tuple[str, float, float, float, float]] = []
    for item in items:
        try:
            name = str(item["name"]).strip()
            cal   = float(item["calories"])
            prot  = float(item["protein"])
            fat   = float(item["fat"])
            carbs = float(item["carbs"])
        except (KeyError, TypeError, ValueError):
            continue

        if not name or len(name) < 2:
            continue
        if not (1 <= cal <= 950):
            continue
        if any(v < 0 for v in (prot, fat, carbs)):
            continue

        results.append((name, round(cal, 1), round(prot, 1), round(fat, 1), round(carbs, 1)))

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
) -> int:
    """Insert unique products into food_products. Returns count inserted."""
    if not products:
        logger.info("Nothing to insert.")
        return 0

    if dry_run:
        # Deduplicate within the batch only — no DB access
        seen: set[str] = set()
        unique = []
        for row in products:
            key = row[0].lower()
            if key not in seen:
                seen.add(key)
                unique.append(row)
        print(f"\nDRY-RUN — {len(unique)} unique products generated:\n")
        _print_products(unique[:40])
        if len(unique) > 40:
            print(f"\n  … and {len(unique) - 40} more (use without --dry-run to insert all)")
        return 0

    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(FoodProduct.name))
        existing_names = {row[0].lower() for row in existing}
        logger.info("Existing DB products: %d", len(existing_names))

        seen2: set[str] = set()
        new_items: list[FoodProduct] = []
        for name, cal, prot, fat, carbs in products:
            key = name.lower()
            if key in existing_names or key in seen2:
                continue
            seen2.add(key)
            new_items.append(FoodProduct(
                name=name, calories=cal, protein=prot, fat=fat, carbs=carbs
            ))

        if new_items:
            session.add_all(new_items)
            await session.commit()
            logger.info("✓ Inserted %d new products.", len(new_items))
        else:
            logger.info("All products already in DB — nothing inserted.")

        return len(new_items)


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="Generate food products via Gemini")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print results without inserting into DB.",
    )
    parser.add_argument(
        "--categories",
        metavar="INDICES",
        help="Comma-separated category indices to run (0-based). "
             "Default: all categories.",
    )
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY not set.")
        sys.exit(1)

    # Which categories to process
    if args.categories:
        indices = [int(i.strip()) for i in args.categories.split(",")]
        active = [CATEGORIES[i] for i in indices if 0 <= i < len(CATEGORIES)]
    else:
        active = CATEGORIES

    if not args.dry_run:
        await init_db()

    client = genai_sdk.Client(api_key=api_key)
    all_products: list[tuple[str, float, float, float, float]] = []

    for idx, (category, count, hint) in enumerate(active):
        logger.info("[%d/%d] Generating: %s (%d products) …", idx + 1, len(active), category, count)
        rows = await _generate_category(client, category, count, hint)
        logger.info("  → %d valid items received", len(rows))
        all_products.extend(rows)

        # Small pause between requests — avoid rate limiting
        if idx < len(active) - 1:
            await asyncio.sleep(1.5)

    logger.info("\nTotal collected: %d products across %d categories", len(all_products), len(active))
    await insert_products(all_products, dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
