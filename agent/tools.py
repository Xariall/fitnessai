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
QUERY_MAX_LEN = 500
IMAGE_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


def _get_client() -> genai.Client:
    global _client
    if _client is not None:
        return _client
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    _client = genai.Client(api_key=api_key)
    return _client


def _get_collection():
    global _chroma_collection
    if _chroma_collection is not None:
        return _chroma_collection
    db = chromadb.PersistentClient(path=str(CHROMA_DIR))
    _chroma_collection = db.get_collection(COLLECTION_NAME)
    return _chroma_collection


def _strip_markdown_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    return text.split("\n", 1)[1].rsplit("```", 1)[0].strip()


def _parse_json_response(text: str, error_msg: str) -> str:
    text = _strip_markdown_fence(text.strip())
    try:
        return json.dumps(json.loads(text), ensure_ascii=False)
    except json.JSONDecodeError:
        return json.dumps({"error": error_msg, "raw": text}, ensure_ascii=False)


def _embed_query(client: genai.Client, query: str) -> list[float]:
    result = client.models.embed_content(
        model="models/gemini-embedding-001",
        contents=query,
    )
    return result.embeddings[0].values


def _build_chunks(results: dict) -> list[dict]:
    return [
        {
            "text": doc,
            "source": meta.get("source", ""),
            "topic": meta.get("topic", ""),
            "relevance": round(1 - dist, 3),
        }
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    ]


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
    if not query or not query.strip():
        return json.dumps({"error": "Пустой запрос"}, ensure_ascii=False)
    query = query[:QUERY_MAX_LEN]

    try:
        collection = _get_collection()
    except Exception:
        return json.dumps(
            {"error": "База знаний не проиндексирована. Запустите: python -m knowledge.ingest"},
            ensure_ascii=False,
        )

    try:
        embedding = _embed_query(_get_client(), query)
        results = collection.query(
            query_embeddings=[embedding],
            n_results=5,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        return json.dumps({"error": f"Ошибка поиска: {e}"}, ensure_ascii=False)

    if not results["documents"] or not results["documents"][0]:
        return json.dumps({"result": "Ничего не найдено по запросу"}, ensure_ascii=False)

    return json.dumps({"query": query, "results": _build_chunks(results)}, ensure_ascii=False)


def _food_photo_prompt(weight_grams: float) -> str:
    return f"""Ты — эксперт-нутрициолог. Проанализируй фото еды.

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


@tool
async def analyze_food_photo(image_base64: str, weight_grams: float) -> str:
    """Анализирует фото еды через Gemini Vision.
    Определяет блюдо и рассчитывает КБЖУ на указанный вес порции.

    Args:
        image_base64: Фото в формате base64
        weight_grams: Вес порции в граммах
    """
    try:
        image_bytes = base64.b64decode(image_base64)
    except Exception:
        return json.dumps({"error": "Некорректные данные изображения"}, ensure_ascii=False)

    if len(image_bytes) > IMAGE_MAX_BYTES:
        return json.dumps({"error": "Изображение слишком большое (макс. 5 МБ)"}, ensure_ascii=False)

    client = _get_client()
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")
    image_data = base64.b64encode(image_bytes).decode()

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=[
                {"inline_data": {"mime_type": "image/jpeg", "data": image_data}},
                _food_photo_prompt(weight_grams),
            ],
        )
    except Exception as e:
        return json.dumps({"error": f"Ошибка анализа фото: {e}"}, ensure_ascii=False)
    return _parse_json_response(response.text, "Не удалось распознать еду на фото")


def _bmi_category(bmi: float) -> str:
    if bmi < 16:
        return "Выраженный дефицит массы тела"
    if bmi < 18.5:
        return "Дефицит массы тела"
    if bmi < 25:
        return "Нормальная масса тела"
    if bmi < 30:
        return "Избыточная масса тела (предожирение)"
    if bmi < 35:
        return "Ожирение I степени"
    if bmi < 40:
        return "Ожирение II степени"
    return "Ожирение III степени"


@tool
def calculate_bmi(weight_kg: float, height_cm: float) -> str:
    """Рассчитывает индекс массы тела (ИМТ / BMI).

    Args:
        weight_kg: Вес в килограммах
        height_cm: Рост в сантиметрах
    """
    if height_cm <= 0:
        return json.dumps({"error": "Рост должен быть больше нуля"}, ensure_ascii=False)
    bmi = weight_kg / (height_cm / 100) ** 2
    return json.dumps({
        "bmi": round(bmi, 1),
        "category": _bmi_category(bmi),
        "weight_kg": weight_kg,
        "height_cm": height_cm,
    }, ensure_ascii=False)


_GOAL_MAP = {
    "lose": "похудение и жиросжигание",
    "gain": "набор мышечной массы",
    "maintain": "поддержание формы",
    "recomposition": "рекомпозиция тела (снижение жира + рост мышц)",
}
_LEVEL_MAP = {
    "beginner": "новичок (до 6 месяцев опыта)",
    "intermediate": "средний (6-24 месяца опыта)",
    "advanced": "продвинутый (2+ года опыта)",
}


def _workout_prompt(goal: str, level: str, days_per_week: int) -> str:
    return f"""Ты — профессиональный фитнес-тренер. Составь программу тренировок:

- Цель: {_GOAL_MAP.get(goal, goal)}
- Уровень: {_LEVEL_MAP.get(level, level)}
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


@tool
async def generate_workout_plan(goal: str, level: str, days_per_week: int) -> str:
    """Генерирует программу тренировок через Gemini.

    Args:
        goal: Цель — 'lose' (похудение), 'gain' (набор массы), 'maintain' (поддержание), 'recomposition' (рекомпозиция)
        level: Уровень — 'beginner', 'intermediate', 'advanced'
        days_per_week: Количество тренировочных дней в неделю (2-6)
    """
    if days_per_week < 2 or days_per_week > 6:
        return json.dumps({"error": "days_per_week должно быть от 2 до 6"}, ensure_ascii=False)

    client = _get_client()
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=_workout_prompt(goal, level, days_per_week),
        )
    except Exception as e:
        return json.dumps({"error": f"Ошибка генерации программы: {e}"}, ensure_ascii=False)
    return _parse_json_response(response.text, "Не удалось сгенерировать программу")
