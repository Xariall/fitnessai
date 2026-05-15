# Tools — Инструменты агента

Все инструменты реализованы как LangGraph tools (функции с декоратором `@tool`).
Агент выбирает инструменты самостоятельно на основе запроса пользователя.

## Профиль пользователя

### get_user_profile
Получить профиль пользователя из БД.
```
input: telegram_user_id: int
output: {name, age, weight_kg, height_cm, goal, activity_level}
```

### update_user_profile
Обновить одно или несколько полей профиля.
```
input: telegram_user_id: int, fields: dict
output: updated_profile
```

## Тренировки

### generate_workout_plan
Сгенерировать план тренировки на основе профиля и запроса.
```
input: telegram_user_id: int, focus: str (muscle_group или тип: cardio/strength/flexibility), duration_minutes: int
output: workout_plan (сохраняется в workouts)
```

### log_workout
Записать выполненную тренировку.
```
input: telegram_user_id: int, notes: str, workout_id: uuid (optional)
output: confirmation
```

### get_workout_history
Получить историю тренировок пользователя.
```
input: telegram_user_id: int, limit: int (default 5)
output: list of workout_logs
```

### find_exercises
Найти упражнения по группе мышц или типу.
```
input: muscle_group: str, equipment: str (optional)
output: list of exercises with description
```

## Питание

### calculate_daily_calories
Рассчитать суточную норму КБЖУ по формуле Миффлина-Сан Жеора с учётом цели.
```
input: telegram_user_id: int
output: {calories, protein, fat, carbs}
```

### generate_nutrition_plan
Сгенерировать план питания на день с конкретными блюдами.
```
input: telegram_user_id: int, preferences: str (optional — непереносимости, предпочтения)
output: nutrition_plan (сохраняется в nutrition_plans)
```

### log_food
Записать приём пищи.
```
input: telegram_user_id: int, food_name: str, meal_type: str, calories: int, protein: float, fat: float, carbs: float
output: confirmation + дневной итог
```

### get_daily_nutrition_summary
Получить сводку по питанию за сегодня.
```
input: telegram_user_id: int
output: {consumed: {calories, protein, fat, carbs}, remaining: {...}, logs: [...]}
```

### get_food_info
Получить КБЖУ продукта (встроенная база + LLM).
```
input: food_name: str, weight_grams: int (optional)
output: {calories, protein, fat, carbs}
```

## Прогресс

### log_progress
Записать замер веса и заметки.
```
input: telegram_user_id: int, weight_kg: float, notes: str (optional)
output: confirmation + динамика (разница с предыдущим замером)
```

### get_progress_summary
Показать динамику прогресса за период.
```
input: telegram_user_id: int, days: int (default 30)
output: {start_weight, current_weight, delta, logs: [...]}
```

## Мотивация

### send_motivation
Сгенерировать персональное мотивационное сообщение на основе профиля и прогресса.
```
input: telegram_user_id: int
output: motivational_message
```
