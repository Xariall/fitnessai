"""Custom agent tools: Gemini Vision food analysis, BMI, workout plan generation."""

import base64
import json
import os

from langchain_core.tools import tool
from google import genai

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client


@tool
async def analyze_food_photo(image_base64: str, weight_grams: float) -> str:
    """Анализирует фото еды через Gemini Vision.
    Определяет блюдо и рассчитывает КБЖУ на указанный вес порции.

    Args:
        image_base64: Фото в формате base64
        weight_grams: Вес порции в граммах
    """
    client = _get_client()

    image_bytes = base64.b64decode(image_base64)

    prompt = f"""Ты — эксперт-нутрициолог. Проанализируй фото еды.

1. Определи, что на фото (название блюда/продукта)
2. Рассчитай КБЖУ на {weight_grams} грамм порции

Ответь СТРОГО в JSON:
{{
  "product": "название блюда",
  "weight_g": {weight_grams},
  "calories": число,
  "protein": число,
  "fat": число,
  "carbs": число,
  "confidence": "high/medium/low"
}}

Только JSON, без markdown-обёрток."""

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")
    response = client.models.generate_content(
        model=model_name,
        contents=[
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image_bytes).decode()}},
            prompt,
        ],
    )

    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        return json.dumps({"error": "Не удалось распознать еду на фото", "raw": text}, ensure_ascii=False)

    return json.dumps(result, ensure_ascii=False)


@tool
def calculate_bmi(weight_kg: float, height_cm: float) -> str:
    """Рассчитывает индекс массы тела (ИМТ / BMI).

    Args:
        weight_kg: Вес в килограммах
        height_cm: Рост в сантиметрах
    """
    height_m = height_cm / 100
    bmi = weight_kg / (height_m ** 2)

    if bmi < 16:
        category = "Выраженный дефицит массы тела"
    elif bmi < 18.5:
        category = "Дефицит массы тела"
    elif bmi < 25:
        category = "Нормальная масса тела"
    elif bmi < 30:
        category = "Избыточная масса тела (предожирение)"
    elif bmi < 35:
        category = "Ожирение I степени"
    elif bmi < 40:
        category = "Ожирение II степени"
    else:
        category = "Ожирение III степени"

    return json.dumps({
        "bmi": round(bmi, 1),
        "category": category,
        "weight_kg": weight_kg,
        "height_cm": height_cm,
    }, ensure_ascii=False)


@tool
async def generate_workout_plan(goal: str, level: str, days_per_week: int) -> str:
    """Генерирует программу тренировок через Gemini.

    Args:
        goal: Цель — 'lose' (похудение), 'gain' (набор массы), 'maintain' (поддержание), 'recomposition' (рекомпозиция)
        level: Уровень — 'beginner', 'intermediate', 'advanced'
        days_per_week: Количество тренировочных дней в неделю (2-6)
    """
    client = _get_client()

    goal_map = {
        "lose": "похудение и жиросжигание",
        "gain": "набор мышечной массы",
        "maintain": "поддержание формы",
        "recomposition": "рекомпозиция тела (снижение жира + рост мышц)",
    }
    level_map = {
        "beginner": "новичок (до 6 месяцев опыта)",
        "intermediate": "средний (6-24 месяца опыта)",
        "advanced": "продвинутый (2+ года опыта)",
    }

    prompt = f"""Ты — профессиональный фитнес-тренер. Составь программу тренировок:

- Цель: {goal_map.get(goal, goal)}
- Уровень: {level_map.get(level, level)}
- Дней в неделю: {days_per_week}

Ответь СТРОГО в JSON:
{{
  "name": "Название программы",
  "description": "Краткое описание",
  "days": [
    {{
      "day": 1,
      "name": "Название дня (напр. Грудь + Трицепс)",
      "exercises": [
        {{
          "name": "Название упражнения",
          "sets": число,
          "reps": "8-12",
          "rest_sec": 90,
          "notes": "подсказка по технике"
        }}
      ]
    }}
  ]
}}

Используй проверенные упражнения. 4-6 упражнений на день. Только JSON, без markdown."""

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
    )

    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        return json.dumps({"error": "Не удалось сгенерировать программу", "raw": text}, ensure_ascii=False)

    return json.dumps(result, ensure_ascii=False)
