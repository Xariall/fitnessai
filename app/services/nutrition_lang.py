"""Language configs for the nutrition planner.

To add a new language (e.g. Kazakh):
  1. Create a new LanguageConfig instance (copy RU as a template).
  2. Translate every field — see inline `# kk:` comments on the RU config.
  3. Register it in CONFIGS under the ISO-639-1 code ("kk").
  4. Pass lang="kk" to generate_weekly_plan / filter_excluded_products.

Nothing else needs to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LanguageConfig:
    """All language-specific data used by the nutrition planner.

    Keeping every translatable string here means adding a new language
    is a single-file change — no logic files need to be touched.
    """

    code: str  # ISO-639-1, e.g. "ru", "kk"

    # ── Intent detection ──────────────────────────────────────────────────────
    # Words that signal "exclude these products" from the plan.
    exclusion_markers: frozenset[str]

    # Words that signal "use ONLY these products" (whitelist mode).
    inclusion_only_markers: frozenset[str]

    # Connectors / prepositions stripped from product-name candidates.
    # Must include exclusion_markers and inclusion_only_markers so they are
    # not mistakenly matched against product names.
    token_stopwords: frozenset[str]

    # ── Category → product-name stem mapping ─────────────────────────────────
    # Keys are category words users might write (e.g. "рыба").
    # Values are stems that appear inside product names in the DB.
    # Stems are matched with startswith, so short stems cover inflected forms.
    category_keywords: dict[str, list[str]]

    # ── Gemini prompt strings ─────────────────────────────────────────────────
    # Localized goal labels keyed by internal code.
    goal_labels: dict[str, str]  # keys: "lose" | "gain" | "maintain"

    # Full system prompt sent to Gemini (static — no interpolation needed).
    system_prompt: str

    # User message template. Available placeholders:
    #   {goal}      — localized goal label
    #   {calories}  — target kcal/day (int)
    #   {protein}   — grams of protein (int)
    #   {fat}       — grams of fat (int)
    #   {carbs}     — grams of carbs (int)
    #   {products}  — compact product catalogue string
    #   {notes_line}— formatted notes line (see notes_present / notes_absent)
    user_message_tpl: str

    # How to format the notes line when the user provided notes.
    # Placeholder: {notes}
    notes_present_tpl: str

    # Static string used when the user provided no notes.
    notes_absent: str


# ── Russian ───────────────────────────────────────────────────────────────────

_RU_EXCLUSION_MARKERS: frozenset[str] = frozenset({
    "без", "исключить", "убрать", "исключи", "убери", "кроме",
    # kk: жоқ, алып тастау, алып тасташы, бөлек
})

_RU_INCLUSION_ONLY_MARKERS: frozenset[str] = frozenset({
    "только", "лишь", "исключительно",
    # kk: тек, ғана, тек қана
})

_RU_TOKEN_STOPWORDS: frozenset[str] = frozenset({
    "и", "а", "также", "не", "нет", "с", "для", "на", "в", "из",
    "по", "или", "но", "при", "ещё", "еще", "всё", "все",
}) | _RU_EXCLUSION_MARKERS | _RU_INCLUSION_ONLY_MARKERS

_RU_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    # kk equivalents noted inline for future translation
    "рыба": [          # kk: балық
        "тунец", "лосось", "сёмга", "семга", "скумбрия", "треска",
        "минтай", "горбуша", "сардина", "форель", "хек", "судак",
        "карп", "окунь", "килька", "шпрот", "анчоус", "дорадо",
        "сибас", "пикша", "навага", "камбала", "рыба",
    ],
    "морепродукты": [  # kk: теңіз өнімдері
        "креветк", "кальмар", "осьминог", "мидий", "краб",
        "омар", "гребешок", "морепродукт",
    ],
    "мясо": [          # kk: ет
        "говядин", "говяж", "свинин", "свиной", "баранин", "телятин",
        "кролик", "индейк", "утк", "гусь", "оленин", "конин",
        "фарш", "мясо",
    ],
    "курица": [        # kk: тауық
        "куриц", "куриная", "курин", "цыплён",
    ],
    "птица": [         # kk: құс
        "куриц", "куриная", "курин", "индейк", "утк", "гусь",
        "цыплён", "перепел",
    ],
    "молочное": [      # kk: сүт өнімдері
        "молок", "кефир", "ряженк", "простоквашь", "йогурт",
        "творог", "сметан", "сливк", "масл", "сыр", "пармезан",
        "моцарелл", "рикотт", "брынз",
    ],
    "молоко": [        # kk: сүт
        "молок", "кефир", "ряженк",
    ],
    "сыр": [           # kk: ірімшік
        "сыр", "пармезан", "моцарелл", "рикотт", "брынз", "фет",
    ],
    "яйца": [          # kk: жұмыртқа
        "яйц", "яйко", "яичн",
    ],
    "крупы": [         # kk: дәнді дақылдар
        "гречк", "овсянк", "рис", "пшен", "ячмен", "перловк",
        "манк", "кукурузн", "булгур", "кускус", "полба",
    ],
    "бобовые": [       # kk: бұршақ тұқымдастар
        "фасол", "нут", "чечевиц", "горох", "соя", "маш", "эдамам",
    ],
    "глютен": [        # kk: глютен
        "пшениц", "рожь", "ячмен", "манк", "булгур", "кускус",
        "макарон", "паст", "лапш", "хлеб", "батон", "булк",
        "сухар", "крекер", "муки", "мука",
    ],
    "овощи": [         # kk: көкөністер
        "капуст", "морков", "помидор", "томат", "огурец", "перец",
        "кабачок", "баклажан", "свёкл", "свекл", "тыкв", "редис",
        "сельдерей", "шпинат", "листь", "зелень", "укроп", "петрушк",
    ],
    "фрукты": [        # kk: жемістер
        "яблок", "груш", "апельсин", "мандарин", "лимон", "банан",
        "виноград", "слив", "персик", "абрикос", "черешн", "вишн",
        "клубник", "малин", "черник", "голубик", "смородин",
    ],
    "ягоды": [         # kk: жидектер
        "клубник", "малин", "черник", "голубик", "смородин",
        "ежевик", "клюкв", "брусник", "вишн", "черешн",
    ],
    "орехи": [         # kk: жаңғақтар
        "арахис", "миндал", "грецк", "кешью", "фундук", "фисташк",
        "пекан", "макадами", "орех",
    ],
    "сладкое": [       # kk: тәттілер
        "шоколад", "конфет", "торт", "пирог", "печень", "вафл",
        "мармелад", "зефир", "халв", "карамел", "сахар", "мёд", "мед",
    ],
}

_RU_GOAL_LABELS: dict[str, str] = {
    "lose":     "похудение",      # kk: арықтау
    "gain":     "набор массы",    # kk: салмақ қосу
    "maintain": "поддержание веса",  # kk: салмақты сақтау
}

_RU_SYSTEM_PROMPT = (
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
    # kk: translate this entire prompt to Kazakh
)

_RU_USER_MESSAGE_TPL = (
    "Цель: {goal} | КБЖУ/день: {calories}ккал, "
    "Б:{protein}г, Ж:{fat}г, У:{carbs}г\n"
    "Продукты: {products}\n"
    "{notes_line}"
    # kk: translate labels (Цель→Мақсат, КБЖУ→КБЖМ, Продукты→Өнімдер, etc.)
)

RU = LanguageConfig(
    code="ru",
    exclusion_markers=_RU_EXCLUSION_MARKERS,
    inclusion_only_markers=_RU_INCLUSION_ONLY_MARKERS,
    token_stopwords=_RU_TOKEN_STOPWORDS,
    category_keywords=_RU_CATEGORY_KEYWORDS,
    goal_labels=_RU_GOAL_LABELS,
    system_prompt=_RU_SYSTEM_PROMPT,
    user_message_tpl=_RU_USER_MESSAGE_TPL,
    notes_present_tpl="Заметки (строго соблюдай): {notes}",  # kk: Ескертпелер (міндетті түрде орында): {notes}
    notes_absent="Заметки: нет",                              # kk: Ескертпелер: жоқ
)


# ── Kazakh skeleton (fill in when adding kk UI) ───────────────────────────────
# Uncomment and translate when ready.
#
# KK = LanguageConfig(
#     code="kk",
#     exclusion_markers=frozenset({"жоқ", "алып тастау", "алып тасташы", "бөлек"}),
#     inclusion_only_markers=frozenset({"тек", "ғана", "тек қана"}),
#     token_stopwords=frozenset({
#         "және", "мен", "сонымен", "бірге", "үшін", "да", "де",
#     }) | exclusion_markers | inclusion_only_markers,
#     category_keywords={
#         "балық": ["тунец", "лосось", ...],   # same DB stems, only keys differ
#         "ет": ["говядин", "говяж", ...],
#         # ... (add all categories)
#     },
#     goal_labels={"lose": "арықтау", "gain": "салмақ қосу", "maintain": "салмақты сақтау"},
#     system_prompt="...",   # translate _RU_SYSTEM_PROMPT to Kazakh
#     user_message_tpl="Мақсат: {goal} | КБЖМ/күн: {calories}ккал, ...",
#     notes_present_tpl="Ескертпелер (міндетті түрде орында): {notes}",
#     notes_absent="Ескертпелер: жоқ",
# )


# ── Registry ──────────────────────────────────────────────────────────────────

CONFIGS: dict[str, LanguageConfig] = {
    "ru": RU,
    # "kk": KK,  # uncomment when KK is ready
}


def get_config(lang: str) -> LanguageConfig:
    """Return the LanguageConfig for *lang*, falling back to Russian."""
    return CONFIGS.get(lang, RU)
