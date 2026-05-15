# Database — Схема БД

## Платформа
Supabase (PostgreSQL). Все таблицы в схеме `public`.

## Таблицы

### users
Профиль пользователя. Создаётся при онбординге.

| Колонка | Тип | Описание |
|---------|-----|----------|
| id | uuid (PK) | Внутренний ID |
| telegram_user_id | bigint (unique) | ID из Telegram |
| name | text | Имя пользователя |
| age | int | Возраст |
| weight_kg | float | Текущий вес (кг) |
| height_cm | float | Рост (см) |
| goal | text | Цель: `lose_weight` / `gain_muscle` / `maintain` |
| activity_level | text | `sedentary` / `light` / `moderate` / `active` / `very_active` |
| created_at | timestamptz | Дата регистрации |
| updated_at | timestamptz | Дата обновления |

### workouts
Планы тренировок, сгенерированные агентом.

| Колонка | Тип | Описание |
|---------|-----|----------|
| id | uuid (PK) | — |
| user_id | uuid (FK → users) | — |
| title | text | Название плана |
| plan | jsonb | Структура плана (упражнения, подходы, повторения) |
| created_at | timestamptz | — |

### workout_logs
Выполненные тренировки (записи пользователя).

| Колонка | Тип | Описание |
|---------|-----|----------|
| id | uuid (PK) | — |
| user_id | uuid (FK → users) | — |
| workout_id | uuid (FK → workouts, nullable) | Ссылка на план если был |
| notes | text | Заметки пользователя |
| completed_at | timestamptz | Когда выполнена |

### nutrition_plans
Планы питания, сгенерированные агентом.

| Колонка | Тип | Описание |
|---------|-----|----------|
| id | uuid (PK) | — |
| user_id | uuid (FK → users) | — |
| target_calories | int | Целевые калории |
| target_protein | float | Белки (г) |
| target_fat | float | Жиры (г) |
| target_carbs | float | Углеводы (г) |
| plan | jsonb | Рацион по приёмам пищи |
| created_at | timestamptz | — |

### food_logs
Записи приёмов пищи пользователя.

| Колонка | Тип | Описание |
|---------|-----|----------|
| id | uuid (PK) | — |
| user_id | uuid (FK → users) | — |
| food_name | text | Название продукта/блюда |
| calories | int | Калории |
| protein | float | Белки (г) |
| fat | float | Жиры (г) |
| carbs | float | Углеводы (г) |
| meal_type | text | `breakfast` / `lunch` / `dinner` / `snack` |
| logged_at | timestamptz | — |

### progress_logs
Замеры прогресса пользователя.

| Колонка | Тип | Описание |
|---------|-----|----------|
| id | uuid (PK) | — |
| user_id | uuid (FK → users) | — |
| weight_kg | float | Вес (кг) |
| notes | text | Заметки |
| measured_at | timestamptz | Дата замера |
