"""CRUD helpers — async SQLAlchemy.

MCP servers call these functions directly (as sub-processes), so every
function opens its own short-lived session rather than sharing one.

Fitness user_id convention
--------------------------
The LangGraph agent injects ``user_id`` (an integer PK) into the system
prompt as a string.  MCP tool parameters carry it as ``str``; the helpers
below convert it to ``int`` before every DB call.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

def _now() -> datetime:
    return datetime.utcnow()

from sqlalchemy import delete, func, select, update

from database.engine import AsyncSessionLocal
from database.models import (
    Conversation,
    Exercise,
    FoodDiary,
    FoodProduct,
    MealPlanItem,
    Message,
    NutritionPlan,
    User,
    Waitlist,
    WeightLog,
    WorkoutLog,
    WorkoutProgram,
)


def _uid(user_id: str | int) -> int:
    return int(user_id)


# ── Users ────────────────────────────────────────────────────────────────────

async def get_or_create_user(
    google_id: str,
    email: str | None = None,
    name: str | None = None,
    picture: str | None = None,
) -> User:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.google_id == google_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.email = email or user.email
            user.name = name or user.name
            user.picture = picture or user.picture
            user.updated_at = _now()
            await session.commit()
            await session.refresh(user)
            return user

        user = User(google_id=google_id, email=email, name=name, picture=picture)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def get_user_by_google_id(google_id: str) -> User | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.google_id == google_id)
        )
        return result.scalar_one_or_none()


async def get_user_by_id(user_id: int) -> User | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


async def get_user(user_id: str) -> dict | None:
    """Compat helper used by MCP nutrition server."""
    user = await get_user_by_id(_uid(user_id))
    if not user:
        return None
    return {
        "id": user.id,
        "name": user.name,
        "age": user.age,
        "height": user.height,
        "weight": user.weight,
        "gender": user.gender,
        "activity": user.activity,
        "goal": user.goal,
    }


async def upsert_user_profile(user_id: int, **fields) -> dict:
    allowed = {"name", "age", "height", "weight", "gender", "activity", "goal", "injuries", "onboarding_completed"}
    filtered = {k: v for k, v in fields.items() if k in allowed and v is not None}
    async with AsyncSessionLocal() as session:
        if filtered:
            await session.execute(
                update(User).where(User.id == user_id).values(**filtered, updated_at=_now())
            )
            await session.commit()
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "id": user.id,
            "name": user.name,
            "age": user.age,
            "height": user.height,
            "weight": user.weight,
            "gender": user.gender,
            "activity": user.activity,
            "goal": user.goal,
        }


# ── Weight ───────────────────────────────────────────────────────────────────

async def log_weight(user_id: str, weight: float) -> None:
    uid = _uid(user_id)
    async with AsyncSessionLocal() as session:
        session.add(WeightLog(user_id=uid, weight=weight))
        # Keep profile weight in sync
        await session.execute(
            update(User).where(User.id == uid).values(weight=weight, updated_at=_now())
        )
        await session.commit()


async def get_weight_history(user_id: str, days: int = 30) -> list[dict]:
    uid = _uid(user_id)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WeightLog)
            .where(WeightLog.user_id == uid, WeightLog.logged_at >= since)
            .order_by(WeightLog.logged_at.desc())
        )
        return [
            {"weight": row.weight, "logged_at": row.logged_at.isoformat()}
            for row in result.scalars()
        ]


# ── Exercises ────────────────────────────────────────────────────────────────

async def get_exercises(muscle_group: str | None = None) -> list[dict]:
    async with AsyncSessionLocal() as session:
        q = select(Exercise)
        if muscle_group:
            q = q.where(Exercise.muscle_group == muscle_group)
        result = await session.execute(q)
        return [
            {
                "id": e.id,
                "name": e.name,
                "muscle_group": e.muscle_group,
                "equipment": e.equipment,
                "description": e.description,
            }
            for e in result.scalars()
        ]


# ── Workout programs ─────────────────────────────────────────────────────────

async def save_workout_program(
    user_id: str, name: str, goal: str, level: str, days: int, program_json: str
) -> int:
    uid = _uid(user_id)
    async with AsyncSessionLocal() as session:
        prog = WorkoutProgram(
            user_id=uid, name=name, goal=goal,
            level=level, days_per_week=days, program_json=program_json,
        )
        session.add(prog)
        await session.commit()
        await session.refresh(prog)
        return prog.id


async def get_workout_programs(user_id: str) -> list[dict]:
    uid = _uid(user_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WorkoutProgram)
            .where(WorkoutProgram.user_id == uid)
            .order_by(WorkoutProgram.created_at.desc())
        )
        return [
            {
                "id": p.id,
                "name": p.name,
                "goal": p.goal,
                "level": p.level,
                "days_per_week": p.days_per_week,
                "program_json": p.program_json,
                "created_at": p.created_at.isoformat(),
            }
            for p in result.scalars()
        ]


# ── Workout logs ─────────────────────────────────────────────────────────────

async def log_workout(
    user_id: str, exercise: str, sets: int, reps: int, weight_kg: float | None = None
) -> None:
    uid = _uid(user_id)
    async with AsyncSessionLocal() as session:
        session.add(WorkoutLog(
            user_id=uid, exercise=exercise, sets=sets, reps=reps, weight_kg=weight_kg
        ))
        await session.commit()


async def get_workout_logs(user_id: str, date: str | None = None) -> list[dict]:
    uid = _uid(user_id)
    async with AsyncSessionLocal() as session:
        q = select(WorkoutLog).where(WorkoutLog.user_id == uid)
        if date:
            try:
                day = datetime.strptime(date, "%Y-%m-%d").date()
            except ValueError:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")
            q = q.where(func.date(WorkoutLog.logged_at) == day)
        q = q.order_by(WorkoutLog.logged_at.desc()).limit(50)
        result = await session.execute(q)
        return [
            {
                "id": w.id,
                "exercise": w.exercise,
                "sets": w.sets,
                "reps": w.reps,
                "weight_kg": w.weight_kg,
                "logged_at": w.logged_at.isoformat(),
            }
            for w in result.scalars()
        ]


# ── Food products ─────────────────────────────────────────────────────────────

async def search_food(query: str) -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(FoodProduct).where(FoodProduct.name.ilike(f"%{query}%"))
        )
        return [
            {
                "id": p.id,
                "name": p.name,
                "calories": p.calories,
                "protein": p.protein,
                "fat": p.fat,
                "carbs": p.carbs,
            }
            for p in result.scalars()
        ]


async def get_all_foods() -> list[dict]:
    """Return all products from food_products table."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(FoodProduct))
        return [
            {"id": p.id, "name": p.name, "calories": p.calories,
             "protein": p.protein, "fat": p.fat, "carbs": p.carbs}
            for p in result.scalars()
        ]


# ── Food diary ────────────────────────────────────────────────────────────────

async def log_meal(
    user_id: str, product_name: str, weight_g: float,
    calories: float, protein: float, fat: float, carbs: float,
) -> None:
    uid = _uid(user_id)
    async with AsyncSessionLocal() as session:
        session.add(FoodDiary(
            user_id=uid, product_name=product_name, weight_g=weight_g,
            calories=calories, protein=protein, fat=fat, carbs=carbs,
        ))
        await session.commit()


async def get_food_diary(user_id: str, date: str | None = None) -> list[dict]:
    uid = _uid(user_id)
    async with AsyncSessionLocal() as session:
        q = select(FoodDiary).where(FoodDiary.user_id == uid)
        if date:
            try:
                day = datetime.strptime(date, "%Y-%m-%d").date()
            except ValueError:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")
            q = q.where(func.date(FoodDiary.logged_at) == day)
        else:
            today = _now().date()
            q = q.where(func.date(FoodDiary.logged_at) == today)
        result = await session.execute(q.order_by(FoodDiary.logged_at))
        return [
            {
                "id": e.id,
                "product_name": e.product_name,
                "weight_g": e.weight_g,
                "calories": e.calories,
                "protein": e.protein,
                "fat": e.fat,
                "carbs": e.carbs,
                "logged_at": e.logged_at.isoformat(),
            }
            for e in result.scalars()
        ]


async def get_daily_summary(user_id: str, date: str | None = None) -> dict:
    entries = await get_food_diary(user_id, date)
    totals: dict[str, float | int] = {"calories": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0, "meals": len(entries)}
    for e in entries:
        totals["calories"] += e["calories"]
        totals["protein"] += e["protein"]
        totals["fat"] += e["fat"]
        totals["carbs"] += e["carbs"]
    for k in ("calories", "protein", "fat", "carbs"):
        totals[k] = round(float(totals[k]), 1)
    return totals


# ── Nutrition plans ───────────────────────────────────────────────────────────

async def get_nutrition_plan(user_id: int, date: str) -> dict | None:
    from datetime import date as date_type
    try:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        return None
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(NutritionPlan).where(
                NutritionPlan.user_id == user_id,
                NutritionPlan.date == day,
            )
        )
        plan = result.scalar_one_or_none()
        if not plan:
            return None
        items_result = await session.execute(
            select(MealPlanItem)
            .where(MealPlanItem.plan_id == plan.id)
            .order_by(MealPlanItem.order_index)
        )
        items = items_result.scalars().all()
        meals: dict[str, list[dict]] = {}
        for item in items:
            meal_type = item.meal_type or "other"
            meals.setdefault(meal_type, []).append({
                "id": item.id,
                "meal_type": item.meal_type,
                "product_name": item.product_name,
                "weight_g": item.weight_g,
                "calories": item.calories,
                "protein": item.protein,
                "fat": item.fat,
                "carbs": item.carbs,
                "order_index": item.order_index,
            })
        return {
            "id": plan.id,
            "user_id": plan.user_id,
            "date": plan.date.isoformat(),
            "generated_by": plan.generated_by,
            "notes": plan.notes,
            "meals": meals,
            "created_at": plan.created_at.isoformat(),
            "updated_at": plan.updated_at.isoformat(),
        }


async def create_nutrition_plan(
    user_id: int,
    date: str,
    meals: list[dict],
    notes: str | None = None,
    generated_by: str = "agent",
) -> dict:
    try:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"Invalid date format: {date!r}, expected YYYY-MM-DD")
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(NutritionPlan).where(
                NutritionPlan.user_id == user_id,
                NutritionPlan.date == day,
            )
        )
        plan = result.scalar_one_or_none()
        if plan:
            await session.execute(
                delete(MealPlanItem).where(MealPlanItem.plan_id == plan.id)
            )
            plan.notes = notes
            plan.generated_by = generated_by
            plan.updated_at = _now()
        else:
            plan = NutritionPlan(
                user_id=user_id,
                date=day,
                notes=notes,
                generated_by=generated_by,
                created_at=_now(),
                updated_at=_now(),
            )
            session.add(plan)
            await session.flush()

        for i, meal in enumerate(meals):
            session.add(MealPlanItem(
                plan_id=plan.id,
                meal_type=meal.get("meal_type"),
                product_name=meal["product_name"],
                weight_g=float(meal["weight_g"]),
                calories=float(meal["calories"]),
                protein=float(meal["protein"]),
                fat=float(meal["fat"]),
                carbs=float(meal["carbs"]),
                order_index=i,
            ))
        await session.commit()
        await session.refresh(plan)

    return await get_nutrition_plan(user_id, date)  # type: ignore[return-value]


async def update_plan_item(item_id: int, weight_g: float) -> dict | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(MealPlanItem).where(MealPlanItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        if not item:
            return None

        food_result = await session.execute(
            select(FoodProduct).where(FoodProduct.name.ilike(f"%{item.product_name}%"))
        )
        food = food_result.scalars().first()

        if food:
            ratio = weight_g / 100.0
            calories = round(food.calories * ratio, 1)
            protein = round(food.protein * ratio, 1)
            fat = round(food.fat * ratio, 1)
            carbs = round(food.carbs * ratio, 1)
        else:
            ratio = weight_g / item.weight_g if item.weight_g else 1.0
            calories = round(item.calories * ratio, 1)
            protein = round(item.protein * ratio, 1)
            fat = round(item.fat * ratio, 1)
            carbs = round(item.carbs * ratio, 1)

        await session.execute(
            update(MealPlanItem)
            .where(MealPlanItem.id == item_id)
            .values(
                weight_g=weight_g,
                calories=calories,
                protein=protein,
                fat=fat,
                carbs=carbs,
            )
        )
        await session.commit()

        return {
            "id": item_id,
            "product_name": item.product_name,
            "meal_type": item.meal_type,
            "weight_g": weight_g,
            "calories": calories,
            "protein": protein,
            "fat": fat,
            "carbs": carbs,
            "order_index": item.order_index,
        }


async def calculate_daily_norm(user_id: int) -> dict | None:
    user = await get_user_by_id(user_id)
    if not user or not all([user.weight, user.height, user.age, user.gender, user.activity, user.goal]):
        return None
    weight, height, age = user.weight, user.height, user.age
    gender, activity, goal = user.gender, user.activity, user.goal
    if gender == "male":
        bmr = (10 * weight) + (6.25 * height) - (5 * age) + 5
    else:
        bmr = (10 * weight) + (6.25 * height) - (5 * age) - 161
    multipliers = {"sedentary": 1.2, "moderate": 1.375, "active": 1.55, "athlete": 1.725}
    tdee = bmr * multipliers.get(activity, 1.2)
    adjustments = {"lose": 0.85, "gain": 1.15, "maintain": 1.0, "recomposition": 1.0}
    target = tdee * adjustments.get(goal, 1.0)
    protein = weight * 2.0
    fat = weight * 1.0
    carbs = max((target - (protein * 4) - (fat * 9)) / 4, 50.0)
    return {
        "bmr": round(bmr),
        "tdee": round(tdee),
        "target_calories": round(target),
        "protein_g": round(protein),
        "fat_g": round(fat),
        "carbs_g": round(carbs),
    }


async def add_meal_plan_item(
    plan_id: int,
    meal_type: str | None,
    product_name: str,
    weight_g: float,
    calories: float,
    protein: float,
    fat: float,
    carbs: float,
) -> dict:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.max(MealPlanItem.order_index)).where(MealPlanItem.plan_id == plan_id)
        )
        max_idx = result.scalar() or 0
        item = MealPlanItem(
            plan_id=plan_id,
            meal_type=meal_type,
            product_name=product_name,
            weight_g=weight_g,
            calories=calories,
            protein=protein,
            fat=fat,
            carbs=carbs,
            order_index=max_idx + 1,
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return {
            "id": item.id,
            "plan_id": item.plan_id,
            "meal_type": item.meal_type,
            "product_name": item.product_name,
            "weight_g": item.weight_g,
            "calories": item.calories,
            "protein": item.protein,
            "fat": item.fat,
            "carbs": item.carbs,
            "order_index": item.order_index,
        }


async def delete_meal_plan_item(item_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            delete(MealPlanItem).where(MealPlanItem.id == item_id)
        )
        await session.commit()
        return result.rowcount > 0


async def create_food_product(
    name: str, calories: float, protein: float, fat: float, carbs: float
) -> dict:
    async with AsyncSessionLocal() as session:
        product = FoodProduct(name=name, calories=calories, protein=protein, fat=fat, carbs=carbs)
        session.add(product)
        await session.commit()
        await session.refresh(product)
        return {
            "id": product.id,
            "name": product.name,
            "calories": product.calories,
            "protein": product.protein,
            "fat": product.fat,
            "carbs": product.carbs,
        }


# ── Conversations & messages ──────────────────────────────────────────────────

async def create_conversation(user_id: int, title: str = "Новый чат") -> Conversation:
    async with AsyncSessionLocal() as session:
        conv = Conversation(user_id=user_id, title=title)
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
        return conv


async def get_conversations(user_id: int) -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
        )
        return [
            {
                "id": c.id,
                "title": c.title,
                "created_at": c.created_at.isoformat(),
                "updated_at": c.updated_at.isoformat(),
            }
            for c in result.scalars()
        ]


async def get_conversation(conversation_id: int, user_id: int) -> Conversation | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()


async def get_messages(conversation_id: int) -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        return [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
            }
            for m in result.scalars()
        ]


async def add_message(conversation_id: int, role: str, content: str) -> Message:
    async with AsyncSessionLocal() as session:
        msg = Message(conversation_id=conversation_id, role=role, content=content)
        session.add(msg)
        # Touch updated_at on conversation
        await session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=_now())
        )
        await session.commit()
        await session.refresh(msg)
        return msg


async def get_and_set_system_msg_flag(conversation_id: int) -> bool:
    """Return True if system message was NOT yet sent (first message); atomically sets the flag."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if not conv:
            return False
        if conv.system_msg_sent:
            return False
        conv.system_msg_sent = True
        await session.commit()
        return True


async def update_conversation_title(conversation_id: int, title: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(title=title)
        )
        await session.commit()


# ── Waitlist ──────────────────────────────────────────────────────────────────

async def add_to_waitlist(email: str, name: str | None = None) -> bool:
    """Returns True if newly added, False if already present."""
    async with AsyncSessionLocal() as session:
        existing = await session.execute(
            select(Waitlist).where(Waitlist.email == email)
        )
        if existing.scalar_one_or_none():
            return False
        session.add(Waitlist(email=email, name=name))
        await session.commit()
        return True
