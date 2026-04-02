"""Custom agent tools: Gemini Vision food analysis, BMI, workout plan generation, RAG knowledge search."""

import base64
import json
import os
from pathlib import Path

import chromadb
from langchain_core.tools import tool
from google import genai

_client: genai.Client | None = None
_chroma_collection = None

PROJECT_ROOT = Path(__file__).parent.parent
CHROMA_DIR = PROJECT_ROOT / "chroma_db"
COLLECTION_NAME = "fitness_knowledge"


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client


def _get_collection():
    global _chroma_collection
    if _chroma_collection is None:
        db = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _chroma_collection = db.get_collection(COLLECTION_NAME)
    return _chroma_collection


@tool
async def search_knowledge(query: str) -> str:
    """Поиск по экспертной базе знаний: биомеханика упражнений, противопоказания,
    принципы программирования тренировок, профилактика травм, научные основы питания,
    особенности тренировок для особых групп (пожилые, подростки, беременные, ожирение).

    Используй этот инструмент когда нужно:
    - Проверить противопоказания перед составлением программы
    - Узнать правильную технику или биомеханику упражнения
    - Получить научно обоснованные рекомендации по питанию
    - Учесть особенности для конкретной группы населения
    - Получить информацию о профилактике травм

    Args:
        query: Поисковый запрос на русском языке
    """
    try:
        collection = _get_collection()
    except Exception:
        return json.dumps(
            {"error": "База знаний не проиндексирована. Запустите: python -m knowledge.ingest"},
            ensure_ascii=False,
        )

    client = _get_client()
    embed_result = client.models.embed_content(
        model="models/gemini-embedding-001",
        contents=query,
    )
    query_embedding = embed_result.embeddings[0].values

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=5,
        include=["documents", "metadatas", "distances"],
    )

    if not results["documents"] or not results["documents"][0]:
        return json.dumps({"result": "Ничего не найдено по запросу"}, ensure_ascii=False)

    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append({
            "text": doc,
            "source": meta.get("source", ""),
            "topic": meta.get("topic", ""),
            "relevance": round(1 - dist, 3),
        })

    return json.dumps({"query": query, "results": chunks}, ensure_ascii=False)


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
