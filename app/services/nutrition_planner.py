"""Gemini-powered weekly meal plan generator."""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
from datetime import date, timedelta

import google.genai as genai_sdk
from google.genai import types as genai_types

logger = logging.getLogger(__name__)


# Words that signal "exclude these products"
_EXCLUSION_MARKERS = {"без", "исключить", "убрать", "исключи", "убери", "кроме"}

# Words that signal "use ONLY these products" (whitelist mode)
_INCLUSION_ONLY_MARKERS = {"только", "лишь", "исключительно"}

# Connectors and prepositions filtered out of product-name candidates
_TOKEN_STOPWORDS = {
    "и", "а", "также", "не", "нет", "с", "для", "на", "в", "из",
    "по", "или", "но", "при", "ещё", "еще", "всё", "все",
} | _EXCLUSION_MARKERS | _INCLUSION_ONLY_MARKERS

# Maps category/group words → keywords that appear in product names.
# When a user writes "без рыбы", all products whose name contains any of
# the listed keywords are excluded.
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    # fish & seafood
    "рыба":      ["тунец", "лосось", "сёмга", "семга", "скумбрия", "треска",
                  "минтай", "горбуша", "сардина", "форель", "хек", "судак",
                  "карп", "окунь", "килька", "шпрот", "анчоус", "дорадо",
                  "сибас", "пикша", "навага", "камбала", "рыба"],
    "морепродукты": ["креветк", "кальмар", "осьминог", "мидий", "краб",
                     "омар", "гребешок", "морепродукт"],
    # meat
    "мясо":      ["говядин", "говяж", "свинин", "свиной", "баранин", "телятин",
                  "кролик", "индейк", "утк", "гусь", "оленин", "конин",
                  "фарш", "мясо"],
    "курица":    ["куриц", "куриная", "курин", "цыплён"],
    "птица":     ["куриц", "куриная", "курин", "индейк", "утк", "гусь",
                  "цыплён", "перепел"],
    # dairy
    "молочное":  ["молок", "кефир", "ряженк", "простоквашь", "йогурт",
                  "творог", "сметан", "сливк", "масл", "сыр", "пармезан",
                  "моцарелл", "рикотт", "брынз"],
    "молоко":    ["молок", "кефир", "ряженк"],
    "сыр":       ["сыр", "пармезан", "моцарелл", "рикотт", "брынз", "фет"],
    # eggs
    "яйца":      ["яйц", "яйко", "яичн"],
    # grains & legumes
    "крупы":     ["гречк", "овсянк", "рис", "пшен", "ячмен", "перловк",
                  "манк", "кукурузн", "булгур", "кускус", "полба"],
    "бобовые":   ["фасол", "нут", "чечевиц", "горох", "соя", "маш", "эдамам"],
    "глютен":    ["пшениц", "рожь", "ячмен", "манк", "булгур", "кускус",
                  "макарон", "паст", "лапш", "хлеб", "батон", "булк",
                  "сухар", "крекер", "муки", "мука"],
    # vegetables & fruits
    "овощи":     ["капуст", "морков", "помидор", "томат", "огурец", "перец",
                  "кабачок", "баклажан", "свёкл", "свекл", "тыкв", "редис",
                  "сельдерей", "шпинат", "листь", "зелень", "укроп", "петрушк"],
    "фрукты":    ["яблок", "груш", "апельсин", "мандарин", "лимон", "банан",
                  "виноград", "слив", "персик", "абрикос", "черешн", "вишн",
                  "клубник", "малин", "черник", "голубик", "смородин"],
    "ягоды":     ["клубник", "малин", "черник", "голубик", "смородин",
                  "ежевик", "клюкв", "брусник", "вишн", "черешн"],
    # nuts & seeds
    "орехи":     ["арахис", "миндал", "грецк", "кешью", "фундук", "фисташк",
                  "пекан", "макадами", "орех"],
    "сладкое":   ["шоколад", "конфет", "торт", "пирог", "печень", "вафл",
                  "мармелад", "зефир", "халв", "карамел", "сахар", "мёд", "мед"],
}


def _expand_token(token: str) -> list[str]:
    """Return token + any category keywords it resolves to.

    Checks _CATEGORY_KEYWORDS by exact key match and fuzzy key match
    (handles genitive: "рыбы"→"рыба", "мяса"→"мясо").
    """
    expanded = [token]
    for key, keywords in _CATEGORY_KEYWORDS.items():
        # exact or prefix/suffix match on category key
        if token == key or key.startswith(token) or token.startswith(key):
            expanded.extend(keywords)
            continue
        # fuzzy match on key (handles "рыбы"→"рыба" 0.75, "орехов"→"орехи" 0.73)
        if difflib.SequenceMatcher(None, token, key).ratio() >= 0.7:
            expanded.extend(keywords)
    return expanded


def _token_matches_product(token: str, product_name: str, cutoff: float = 0.6) -> bool:
    """Return True if token (or its category expansion) matches any word in product_name.

    Two matching modes:
    - Original token: fuzzy match (cutoff=0.6) + prefix, to handle inflected forms
      like "курицы"→"куриная" or "шоколада"→"шоколад".
    - Category keywords from _expand_token: prefix/substring only (no fuzzy), to
      prevent false positives like "скумбрия"↔"куриная" (ratio=0.67).
    """
    name_words = product_name.lower().split()
    expanded = _expand_token(token)
    category_keywords = expanded[1:]  # everything after the original token

    # 1. Original token — fuzzy allowed
    for word in name_words:
        if token.startswith(word) or word.startswith(token):
            return True
        if difflib.SequenceMatcher(None, token, word).ratio() >= cutoff:
            return True

    # 2. Category keywords — prefix/substring only, no fuzzy
    name_lower = product_name.lower()
    for kw in category_keywords:
        if kw in name_lower:
            return True
        for word in name_words:
            if kw.startswith(word) or word.startswith(kw):
                return True

    return False


def filter_excluded_products(notes: str, products: list[dict]) -> list[dict]:
    """Filter the product catalogue based on user notes.

    Detects one of three modes from the notes text:

    - **blacklist** (triggered by "без", "исключить", "убрать" …):
        removes products whose names match tokens in the notes.
        "без рыбы и нута" → drops all fish products + нут.

    - **whitelist** (triggered by "только", "лишь", "исключительно"):
        keeps ONLY products whose names match tokens in the notes.
        "только курица и рис" → drops everything except курица + рис.

    - **passthrough** (no mode markers found):
        returns the catalogue unchanged; notes are passed to Gemini as-is.

    Both modes handle category words ("рыба" → тунец, лосось, …) and
    Russian inflected forms ("курицы" → куриная, "риса" → рис).
    """
    if not notes.strip():
        return products

    tokens = re.findall(r"[а-яёa-z]{3,}", notes.lower())
    has_exclusion = any(t in _EXCLUSION_MARKERS for t in tokens)
    has_whitelist = any(t in _INCLUSION_ONLY_MARKERS for t in tokens)

    # passthrough — no structural signal; let Gemini interpret the notes
    if not has_exclusion and not has_whitelist:
        return products

    candidates = [t for t in tokens if t not in _TOKEN_STOPWORDS]
    if not candidates:
        return products

    if has_whitelist and not has_exclusion:
        # Whitelist mode: keep only products that match a candidate token
        kept_indices: set[int] = set()
        for i, product in enumerate(products):
            for candidate in candidates:
                if _token_matches_product(candidate, product["name"]):
                    kept_indices.add(i)
                    logger.info(
                        "Whitelist: keeping product %r (matched token %r)",
                        product["name"], candidate,
                    )
                    break

        if not kept_indices:
            # Safety: if nothing matched, don't wipe the whole catalogue
            logger.warning("Whitelist mode matched no products; returning full catalogue")
            return products

        dropped = [p["name"] for i, p in enumerate(products) if i not in kept_indices]
        if dropped:
            logger.info("Whitelist: dropped %d products: %s", len(dropped), dropped)
        return [p for i, p in enumerate(products) if i in kept_indices]

    # Blacklist mode (default when exclusion markers present)
    excluded_indices: set[int] = set()
    for i, product in enumerate(products):
        for candidate in candidates:
            if _token_matches_product(candidate, product["name"]):
                if i not in excluded_indices:
                    excluded_indices.add(i)
                    logger.info(
                        "Blacklist: excluding product %r (matched token %r)",
                        product["name"], candidate,
                    )
                break

    if not excluded_indices:
        return products

    return [p for i, p in enumerate(products) if i not in excluded_indices]


def build_products_string(products: list[dict]) -> str:
    """Build a compact product catalogue string for the Gemini prompt.

    Format: "овсянка(360кк,б12,ж7,у63); куриная грудка(165кк,б31,ж4,у0); ..."
    All nutritional values are rounded to int.
    """
    parts = [
        (
            f"{p['name']}"
            f"({int(round(p['calories']))}кк,"
            f"б{int(round(p['protein']))},"
            f"ж{int(round(p['fat']))},"
            f"у{int(round(p['carbs']))})"
        )
        for p in products
    ]
    return "; ".join(parts)


async def gemini_generate_plan(
    daily_norm: dict,
    products: list[dict],
    notes: str,
) -> dict:
    """Make a single async Gemini call and return the parsed 7-day plan dict.

    Uses response_mime_type='application/json' so the model is guaranteed to
    return valid JSON. Strips any accidental markdown wrapper before parsing.
    """
    target = daily_norm["target_calories"]
    tdee = daily_norm["tdee"]

    if target < tdee * 0.95:
        goal = "похудение"
    elif target > tdee * 1.05:
        goal = "набор массы"
    else:
        goal = "поддержание веса"

    products_str = build_products_string(products)

    system_prompt = (
        "Ты диетолог-ассистент. Составь 7-дневный план питания.\n"
        "Правила:\n"
        "- Используй ТОЛЬКО продукты из списка — никаких других\n"
        "- Каждый день: breakfast, lunch, dinner, snack\n"
        "- breakfast: 2 продукта, lunch: 3, dinner: 2, snack: 1\n"
        "- Подбери вес порций чтобы сумма КБЖУ за день была близка к цели\n"
        "- Не повторяй один продукт в одном приёме пищи два дня подряд\n"
        "- Пожелания пользователя (поле «Заметки») — ОБЯЗАТЕЛЬНЫ к исполнению: "
        "если указано «без X» или «X» упомянут как нежелательный — "
        "никогда не включай этот продукт ни в один день\n"
        "- Ответ ТОЛЬКО валидный JSON без markdown и пояснений"
    )

    notes_line = f"Заметки (строго соблюдай): {notes}" if notes.strip() else "Заметки: нет"
    user_message = (
        f"Цель: {goal} | КБЖУ/день: {target}ккал, "
        f"Б:{daily_norm['protein_g']}г, Ж:{daily_norm['fat_g']}г, У:{daily_norm['carbs_g']}г\n"
        f"Продукты: {products_str}\n"
        f"{notes_line}"
    )

    # Gemini client is created per-call (project convention — no singleton)
    client = genai_sdk.Client(api_key=os.getenv("GEMINI_API_KEY"))
    response = await client.aio.models.generate_content(
        model="gemini-1.5-flash",
        contents=f"{system_prompt}\n\n{user_message}",
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    # Strip markdown wrapper in case the model ignores response_mime_type hint
    clean_text = re.sub(r"```json\s*|```", "", response.text).strip()
    return json.loads(clean_text)


def match_product(name: str, products: list[dict]) -> dict | None:
    """Return the best-matching product dict for a given name.

    Strategy:
      1. Exact case-insensitive match
      2. difflib fuzzy match with cutoff=0.6
      3. None — caller should skip the item
    """
    name_lower = name.lower()

    # 1. Exact match
    for p in products:
        if p["name"].lower() == name_lower:
            return p

    # 2. Fuzzy match
    names_lower = [p["name"].lower() for p in products]
    close = difflib.get_close_matches(name_lower, names_lower, n=1, cutoff=0.6)
    if close:
        product = next(p for p in products if p["name"].lower() == close[0])
        logger.warning("Fuzzy match: %r → %r", name, product["name"])
        return product

    logger.warning("No product match found for: %r", name)
    return None


def calculate_item_kbju(product: dict, weight_g: float) -> dict:
    """Return a meal-item dict with КБЖУ scaled to the given weight.

    All per-100g values from the product are multiplied by weight_g / 100.
    """
    ratio = weight_g / 100.0
    return {
        "product_id":   product["id"],
        "product_name": product["name"],
        "weight_g":     int(round(weight_g)),
        "calories":     round(product["calories"] * ratio, 1),
        "protein":      round(product["protein"] * ratio, 1),
        "fat":          round(product["fat"] * ratio, 1),
        "carbs":        round(product["carbs"] * ratio, 1),
    }


def adjust_day_portions(
    day_items: list[dict],
    target_calories: int,
    tolerance: float = 0.15,
) -> list[dict]:
    """Proportionally scale all portions if the day's total deviates >±15% from target.

    Returns the original list unchanged when within tolerance.
    """
    if not day_items:
        return day_items

    total = sum(item["calories"] for item in day_items)
    if total == 0:
        return day_items

    if abs(total - target_calories) / target_calories <= tolerance:
        return day_items

    scale = target_calories / total
    logger.info(
        "Scaling day portions: %.0f kcal → %.0f kcal (scale=%.3f)",
        total,
        target_calories,
        scale,
    )
    return [
        {
            **item,
            "weight_g": int(round(item["weight_g"] * scale)),
            "calories": round(item["calories"] * scale, 1),
            "protein":  round(item["protein"]  * scale, 1),
            "fat":      round(item["fat"]       * scale, 1),
            "carbs":    round(item["carbs"]     * scale, 1),
        }
        for item in day_items
    ]


async def generate_weekly_plan(
    daily_norm: dict,
    products: list[dict],
    notes: str,
) -> list[dict]:
    """Orchestrate a 7-day meal plan generation via Gemini.

    Steps:
      1. Call Gemini to get structured JSON for 7 days.
      2. For each day's meal items, fuzzy-match to DB products.
      3. Calculate КБЖУ for each matched item.
      4. Adjust day portions to stay within ±15% of the daily calorie target.
      5. Return a flat list of all items across all 7 days.

    Each returned item has:
        product_id, product_name, weight_g, calories, protein, fat, carbs,
        meal_type, plan_date
    """
    # Strip excluded products from the catalogue before sending to Gemini.
    # This is the primary guardrail — Gemini cannot pick a product it doesn't see.
    filtered_products = filter_excluded_products(notes, products)
    if len(filtered_products) < len(products):
        logger.info(
            "Product catalogue reduced from %d to %d after applying exclusions",
            len(products),
            len(filtered_products),
        )

    result = await gemini_generate_plan(daily_norm, filtered_products, notes)
    today = date.today()
    all_items: list[dict] = []

    for day in result.get("days", []):
        day_number: int = day["day"]
        plan_date = today + timedelta(days=day_number - 1)
        day_items: list[dict] = []

        for meal in day.get("meals", []):
            meal_type: str = meal["meal_type"]

            for raw_item in meal.get("items", []):
                product = match_product(raw_item["product_name"], products)
                if product is None:
                    logger.warning(
                        "Skipping unmatched item %r (day=%d, meal=%s)",
                        raw_item["product_name"],
                        day_number,
                        meal_type,
                    )
                    continue

                kbju = calculate_item_kbju(product, float(raw_item["weight_g"]))
                day_items.append({**kbju, "meal_type": meal_type, "plan_date": plan_date})

        adjusted = adjust_day_portions(day_items, daily_norm["target_calories"])
        all_items.extend(adjusted)

    return all_items
