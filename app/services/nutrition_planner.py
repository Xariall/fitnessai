"""Gemini-powered weekly meal plan generator.

All language-specific strings (markers, category keywords, prompt text)
live in nutrition_lang.py. This module contains only language-agnostic logic.
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
from datetime import date, timedelta

import google.genai as genai_sdk
from google.genai import types as genai_types

from app.services.nutrition_lang import LanguageConfig, get_config

logger = logging.getLogger(__name__)


# ── Token expansion ───────────────────────────────────────────────────────────

def _expand_token(token: str, cfg: LanguageConfig) -> list[str]:
    """Return token + category-keyword stems it resolves to.

    Matches the token against category_keywords keys via prefix and fuzzy
    (cutoff=0.7) to handle inflected forms like "рыбы"→"рыба", "орехов"→"орехи".
    """
    expanded = [token]
    for key, keywords in cfg.category_keywords.items():
        if token == key or key.startswith(token) or token.startswith(key):
            expanded.extend(keywords)
            continue
        if difflib.SequenceMatcher(None, token, key).ratio() >= 0.7:
            expanded.extend(keywords)
    return expanded


def _token_matches_product(
    token: str,
    product_name: str,
    cfg: LanguageConfig,
    cutoff: float = 0.6,
) -> bool:
    """Return True if token (or its category expansion) matches any word in product_name.

    Two matching modes:
    - Original token: fuzzy (cutoff=0.6) + prefix — handles inflected forms
      like "курицы"→"куриная", "шоколада"→"шоколад".
    - Category keywords: prefix/substring only (no fuzzy) — prevents false
      positives like "скумбрия"↔"куриная" (ratio=0.67).
    """
    name_words = product_name.lower().split()
    expanded = _expand_token(token, cfg)
    category_keywords = expanded[1:]

    # 1. Original token — fuzzy allowed
    for word in name_words:
        if token.startswith(word) or word.startswith(token):
            return True
        if difflib.SequenceMatcher(None, token, word).ratio() >= cutoff:
            return True

    # 2. Category keywords — prefix/substring only
    name_lower = product_name.lower()
    for kw in category_keywords:
        if kw in name_lower:
            return True
        for word in name_words:
            if kw.startswith(word) or word.startswith(kw):
                return True

    return False


# ── Product filtering ─────────────────────────────────────────────────────────

def filter_excluded_products(
    notes: str,
    products: list[dict],
    lang: str = "ru",
) -> list[dict]:
    """Filter the product catalogue based on user notes.

    Detects one of three modes from the notes text using cfg markers:

    - **blacklist** (exclusion_markers found — "без", "исключить" …):
        removes products whose names match tokens in the notes.

    - **whitelist** (inclusion_only_markers found — "только", "лишь" …):
        keeps ONLY products whose names match tokens in the notes.

    - **passthrough** (no mode markers found):
        returns the catalogue unchanged; notes are passed to Gemini as-is.

    Both active modes handle category words ("рыба" → тунец, лосось …) and
    inflected forms ("курицы" → куриная, "риса" → рис).
    Adding a new language: pass lang="kk" — all markers come from the config.
    """
    cfg = get_config(lang)

    if not notes.strip():
        return products

    tokens = re.findall(r"\b\w{3,}\b", notes.lower(), re.UNICODE)
    has_exclusion = any(t in cfg.exclusion_markers for t in tokens)
    has_whitelist = any(t in cfg.inclusion_only_markers for t in tokens)

    if not has_exclusion and not has_whitelist:
        return products  # passthrough

    candidates = [t for t in tokens if t not in cfg.token_stopwords]
    if not candidates:
        return products

    if has_whitelist and not has_exclusion:
        # Whitelist: keep only matching products
        kept: set[int] = set()
        for i, product in enumerate(products):
            for candidate in candidates:
                if _token_matches_product(candidate, product["name"], cfg):
                    kept.add(i)
                    logger.info("Whitelist keep: %r ← %r", product["name"], candidate)
                    break

        if not kept:
            logger.warning("Whitelist matched nothing; returning full catalogue")
            return products

        dropped = [p["name"] for i, p in enumerate(products) if i not in kept]
        logger.info("Whitelist dropped %d products: %s", len(dropped), dropped)
        return [p for i, p in enumerate(products) if i in kept]

    # Blacklist: remove matching products
    excluded: set[int] = set()
    for i, product in enumerate(products):
        for candidate in candidates:
            if _token_matches_product(candidate, product["name"], cfg):
                excluded.add(i)
                logger.info("Blacklist exclude: %r ← %r", product["name"], candidate)
                break

    if not excluded:
        return products

    return [p for i, p in enumerate(products) if i not in excluded]


# ── Prompt building ───────────────────────────────────────────────────────────

def build_products_string(products: list[dict]) -> str:
    """Build a compact product catalogue string for the Gemini prompt.

    Format: "овсянка(360кк,б12,ж7,у63); куриная грудка(165кк,б31,ж4,у0); ..."
    Format is fixed (Gemini parses it, not users) — no i18n needed here.
    """
    return "; ".join(
        f"{p['name']}"
        f"({int(round(p['calories']))}кк,"
        f"б{int(round(p['protein']))},"
        f"ж{int(round(p['fat']))},"
        f"у{int(round(p['carbs']))})"
        for p in products
    )


# ── Gemini call ───────────────────────────────────────────────────────────────

_DEFAULT_MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack"]


def _build_meals_line(meal_types: list[str], cfg: LanguageConfig) -> str:
    """Build the 'meal structure' line injected into the Gemini user message.

    Example output: "breakfast (завтрак, 2 блюда), lunch (обед, 3 блюда), dinner (ужин, 2 блюда)"
    """
    parts = []
    for mt in meal_types:
        count = cfg.meal_item_counts.get(mt, 2)
        label = cfg.meal_labels.get(mt, mt)
        noun = "блюдо" if count == 1 else "блюда" if count in (2, 3, 4) else "блюд"
        parts.append(f"{mt} ({label}, {count} {noun})")
    return ", ".join(parts)


async def gemini_generate_plan(
    daily_norm: dict,
    products: list[dict],
    notes: str,
    lang: str = "ru",
    meal_types: list[str] | None = None,
) -> dict:
    """Make a single async Gemini call and return the parsed 7-day plan dict.

    All prompt strings come from the LanguageConfig — no hardcoded Russian text.
    """
    cfg = get_config(lang)
    meal_types = meal_types or _DEFAULT_MEAL_TYPES

    target = daily_norm["target_calories"]
    tdee   = daily_norm["tdee"]

    if target < tdee * 0.95:
        goal = cfg.goal_labels["lose"]
    elif target > tdee * 1.05:
        goal = cfg.goal_labels["gain"]
    else:
        goal = cfg.goal_labels["maintain"]

    notes_line = (
        cfg.notes_present_tpl.format(notes=notes)
        if notes.strip()
        else cfg.notes_absent
    )

    user_message = cfg.user_message_tpl.format(
        goal=goal,
        calories=target,
        protein=daily_norm["protein_g"],
        fat=daily_norm["fat_g"],
        carbs=daily_norm["carbs_g"],
        meals_line=_build_meals_line(meal_types, cfg),
        products=build_products_string(products),
        notes_line=notes_line,
    )

    client = genai_sdk.Client(api_key=os.getenv("GEMINI_API_KEY"))
    response = await client.aio.models.generate_content(
        model="gemini-1.5-flash",
        contents=f"{cfg.system_prompt}\n\n{user_message}",
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    clean_text = re.sub(r"```json\s*|```", "", response.text).strip()
    return json.loads(clean_text)


# ── Product matching & КБЖУ ───────────────────────────────────────────────────

def match_product(name: str, products: list[dict]) -> dict | None:
    """Return the best-matching product dict for a given name.

    1. Exact case-insensitive match
    2. difflib fuzzy match (cutoff=0.6)
    3. None — caller skips the item
    """
    name_lower = name.lower()
    for p in products:
        if p["name"].lower() == name_lower:
            return p

    names_lower = [p["name"].lower() for p in products]
    close = difflib.get_close_matches(name_lower, names_lower, n=1, cutoff=0.6)
    if close:
        product = next(p for p in products if p["name"].lower() == close[0])
        logger.warning("Fuzzy match: %r → %r", name, product["name"])
        return product

    logger.warning("No product match found for: %r", name)
    return None


def calculate_item_kbju(product: dict, weight_g: float) -> dict:
    """Return a meal-item dict with КБЖУ scaled to the given weight."""
    ratio = weight_g / 100.0
    return {
        "product_id":   product["id"],
        "product_name": product["name"],
        "weight_g":     int(round(weight_g)),
        "calories":     round(product["calories"] * ratio, 1),
        "protein":      round(product["protein"]  * ratio, 1),
        "fat":          round(product["fat"]       * ratio, 1),
        "carbs":        round(product["carbs"]     * ratio, 1),
    }


def adjust_day_portions(
    day_items: list[dict],
    target_calories: int,
    tolerance: float = 0.15,
) -> list[dict]:
    """Proportionally scale portions if daily total deviates >±15% from target."""
    if not day_items:
        return day_items

    total = sum(item["calories"] for item in day_items)
    if total == 0:
        return day_items

    if abs(total - target_calories) / target_calories <= tolerance:
        return day_items

    scale = target_calories / total
    logger.info("Scaling portions: %.0f → %.0f kcal (×%.3f)", total, target_calories, scale)
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


# ── Main orchestrator ─────────────────────────────────────────────────────────

async def generate_weekly_plan(
    daily_norm: dict,
    products: list[dict],
    notes: str,
    lang: str = "ru",
    meal_types: list[str] | None = None,
) -> list[dict]:
    """Generate a 7-day meal plan via Gemini.

    Steps:
      1. Filter product catalogue by user notes (blacklist / whitelist / pass).
      2. Call Gemini with the filtered catalogue and localized prompt.
      3. Fuzzy-match Gemini's product names back to DB products.
      4. Scale portions to stay within ±15% of the daily calorie target.
      5. Return a flat list of all items across all 7 days.

    Pass lang="kk" (or any registered code) to switch the full pipeline to
    that language — markers, categories, and prompt all switch automatically.
    Pass meal_types=["lunch","dinner"] to generate a plan without breakfast/snack.
    """
    meal_types = meal_types or _DEFAULT_MEAL_TYPES
    filtered = filter_excluded_products(notes, products, lang=lang)
    if len(filtered) < len(products):
        logger.info(
            "Catalogue: %d → %d products after note-based filtering",
            len(products), len(filtered),
        )

    result = await gemini_generate_plan(daily_norm, filtered, notes, lang=lang, meal_types=meal_types)
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
                        raw_item["product_name"], day_number, meal_type,
                    )
                    continue
                kbju = calculate_item_kbju(product, float(raw_item["weight_g"]))
                day_items.append({**kbju, "meal_type": meal_type, "plan_date": plan_date})

        adjusted = adjust_day_portions(day_items, daily_norm["target_calories"])
        all_items.extend(adjusted)

    return all_items
