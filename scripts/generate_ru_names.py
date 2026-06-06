"""
Одноразовый скрипт генерации русских названий для всех упражнений.

Использование:
    python scripts/generate_ru_names.py              # полная генерация
    python scripts/generate_ru_names.py --update     # только отсутствующие
    python scripts/generate_ru_names.py --batch-size 20  # размер батча (default: 30)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# Добавить корневую директорию проекта в путь
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

EXERCISES_JSON = ROOT / "agent" / "tools" / "exercises.json"
OUTPUT_JSON = ROOT / "agent" / "tools" / "exercises_ru.json"
GOLD_JSON = ROOT / "scripts" / "gold_exercises_ru.json"

_GOLD_PROMPT_EXAMPLES = """
Bench Press → Жим штанги лёжа
Squat → Приседания со штангой
Deadlift → Становая тяга
Pull-Up → Подтягивания
Push-Up → Отжимания от пола
Dumbbell Row → Тяга гантели в наклоне
Overhead Press → Жим штанги стоя
Romanian Deadlift → Румынская тяга
Leg Press → Жим ногами
Seated Cable Row → Тяга нижнего блока сидя
Plank → Планка
Lunge → Выпады
Hip Thrust → Ягодичный мост со штангой
Face Pull → Тяга к лицу
Lat Pulldown → Тяга верхнего блока
""".strip()


def _extract_json(text: str) -> dict:
    """Извлечь JSON из ответа LLM, игнорируя текст до/после."""
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"JSON не найден в ответе: {text[:200]!r}")
    return json.loads(text[start:end])


async def _translate_batch(llm, names: list[str]) -> dict[str, str]:
    """Перевести батч упражнений. Возвращает dict {en_name: ru_name}."""
    template = {name: "" for name in names}
    prompt = (
        "Переведи названия упражнений на профессиональный спортивный русский.\n\n"
        "Правила:\n"
        "- Используй устоявшиеся термины (как в учебниках по физкультуре и тренерской практике)\n"
        "- Максимум 4 слова, без скобок и пояснений\n"
        "- Стиль: именная группа («Жим штанги лёжа», а не «Жать штангу лёжа»)\n\n"
        f"Примеры:\n{_GOLD_PROMPT_EXAMPLES}\n\n"
        "Верни строго JSON без пояснений:\n"
        f"{json.dumps(template, ensure_ascii=False)}"
    )
    try:
        response = await llm.ainvoke(prompt)
        content = response.content or ""
        return _extract_json(content)
    except Exception as exc:
        logger.warning("Батч не удалось перевести (%s): %s", names[:3], exc)
        return {}


async def main(update_only: bool, batch_size: int) -> None:
    from llm.provider import get_llm
    llm = get_llm()

    # Загрузить все английские названия
    exercises = json.loads(EXERCISES_JSON.read_text(encoding="utf-8"))
    all_names = [ex["name"] for ex in exercises]
    logger.info("Всего упражнений: %d", len(all_names))

    # Загрузить существующие переводы
    existing: dict[str, str] = {}
    if OUTPUT_JSON.exists():
        existing = json.loads(OUTPUT_JSON.read_text(encoding="utf-8"))
        logger.info("Загружено существующих переводов: %d", len(existing))

    # Загрузить gold-список (приоритет над LLM)
    gold: dict[str, str] = {}
    if GOLD_JSON.exists():
        gold = json.loads(GOLD_JSON.read_text(encoding="utf-8"))
        logger.info("Gold-список: %d упражнений", len(gold))

    # Определить что нужно переводить
    if update_only:
        to_translate = [n for n in all_names if n not in existing and n not in gold]
    else:
        to_translate = [n for n in all_names if n not in gold]

    logger.info("Требует перевода: %d упражнений", len(to_translate))

    # Разбить на батчи и переводить
    result: dict[str, str] = dict(existing) if update_only else {}
    result.update(gold)  # gold применяется в любом случае

    batches = [to_translate[i:i + batch_size] for i in range(0, len(to_translate), batch_size)]
    logger.info("Батчей: %d по %d упражнений", len(batches), batch_size)

    translated = 0
    failed = 0
    for i, batch in enumerate(batches, 1):
        logger.info("Батч %d/%d (%s...)", i, len(batches), batch[0])
        translations = await _translate_batch(llm, batch)
        for name in batch:
            if name in gold:
                continue  # gold уже применён выше
            ru = translations.get(name, "").strip()
            if ru:
                result[name] = ru
                translated += 1
            else:
                result[name] = name  # fallback: оставить английское
                failed += 1
                logger.warning("Нет перевода для: %s", name)

        # Сохранять после каждого батча
        OUTPUT_JSON.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    logger.info("Готово: %d переведено, %d без перевода (использован EN fallback)", translated, failed)
    logger.info("Сохранено в: %s", OUTPUT_JSON)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Генерация русских названий упражнений")
    parser.add_argument("--update", action="store_true", help="Только отсутствующие переводы")
    parser.add_argument("--batch-size", type=int, default=30, help="Упражнений на батч (default: 30)")
    args = parser.parse_args()

    asyncio.run(main(update_only=args.update, batch_size=args.batch_size))
