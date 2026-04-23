import type { UserProfile } from "@/types/userProfile";

const GENDER_LABELS: Record<string, string> = {
  male: "Мужской",
  female: "Женский",
  other: "Другой",
  prefer_not_to_say: "Не указан",
};

const GOAL_LABELS: Record<string, string> = {
  lose: "Похудеть",
  gain: "Набрать массу",
  maintain: "Поддерживать форму",
  recomposition: "Рекомпозиция (жир ↓ мышцы ↑)",
  endurance: "Улучшить выносливость",
  healthy: "Оставаться здоровым",
  athletic: "Атлетические показатели",
};

const FOOD_BUDGET_GUIDANCE: Record<string, string> = {
  under_5000:
    "Приоритет: дешёвые базовые продукты (овсянка, яйца, куриные бёдра, сезонные овощи). Избегай дорогих добавок и экзотики.",
  "5000_10000":
    "Стандартный супермаркет. Хорошее базовое питание, умеренно разнообразное.",
  "10000_20000":
    "Комфортный бюджет. Можно добавлять качественные белки, рыбу, свежие овощи и фрукты.",
  over_20000:
    "Гибкий бюджет. Доступны премиальные продукты, органика, специальные спортивные продукты.",
};

const TRAINING_BUDGET_GUIDANCE: Record<string, string> = {
  no_budget: "Только упражнения с весом тела. Без оборудования и зала.",
  under_2000: "Базовое домашнее оборудование или тренировки на улице.",
  "2000_5000": "Бюджетный зал. Стандартные тренажёры и свободные веса.",
  "5000_15000": "Хороший зал + периодические групповые занятия.",
  over_15000: "Премиум зал, персональный тренер или спортивная экипировка.",
};

function val(
  v: string | number | null | undefined,
  fallback = "Не указано"
): string {
  if (v === null || v === undefined) return fallback;
  const s = String(v).trim();
  if (s === "" || s.toLowerCase() === "none") return fallback;
  return s;
}

export function buildUserProfileContext(profile: UserProfile): string {
  const gender = GENDER_LABELS[profile.gender ?? ""] ?? val(profile.gender);
  const goal = GOAL_LABELS[profile.goal ?? ""] ?? val(profile.goal);
  const height = profile.height ? `${profile.height} см` : "Не указан";
  const weight = profile.weight ? `${profile.weight} кг` : "Не указан";

  const foodBudgetLabel = val(profile.food_budget);
  const foodBudgetGuidance = profile.food_budget
    ? (FOOD_BUDGET_GUIDANCE[profile.food_budget] ?? "")
    : "";

  const trainingBudgetLabel = val(profile.training_budget);
  const trainingBudgetGuidance = profile.training_budget
    ? (TRAINING_BUDGET_GUIDANCE[profile.training_budget] ?? "")
    : "";

  return [
    "[ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ]",
    `Имя: ${val(profile.name)}`,
    `Пол: ${gender}`,
    `Возраст: ${val(profile.age)}`,
    `Рост: ${height} | Вес: ${weight}`,
    `Цель: ${goal}`,
    "",
    "[ЗДОРОВЬЕ]",
    `Хронические заболевания: ${val(profile.conditions, "Не сообщалось")}`,
    `Травмы/ограничения: ${val(profile.injuries, "Не сообщалось")}`,
    `Пищевые аллергии/непереносимость: ${val(profile.food_allergies, "Не сообщалось")}`,
    "",
    "[ПИТАНИЕ]",
    `Тип питания: ${val(profile.diet_type)}`,
    `Приёмов пищи в день: ${val(profile.meals_per_day)}`,
    `Бюджет на питание: ${foodBudgetLabel}${foodBudgetGuidance ? ` — ${foodBudgetGuidance}` : ""}`,
    "",
    "[ТРЕНИРОВКИ]",
    `Уровень подготовки: ${val(profile.experience_level)}`,
    `Место тренировок: ${val(profile.training_location)}`,
    `Дней в неделю: ${val(profile.training_days)}`,
    `Длительность сессии: ${val(profile.session_duration)}`,
    `Бюджет на тренировки: ${trainingBudgetLabel}${trainingBudgetGuidance ? ` — ${trainingBudgetGuidance}` : ""}`,
  ].join("\n");
}
