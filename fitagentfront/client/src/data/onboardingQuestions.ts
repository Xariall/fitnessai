import type { AnswerValue } from "@/types/userProfile";

// ── Question config types ─────────────────────────────────────────────────────

export type QuestionType =
  | "text"
  | "numeric"
  | "single-select"
  | "multi-select"
  | "none-or-text"
  | "numeric-select";

export interface SelectOption {
  value: string;
  label: string;
  description?: string;
}

export interface NumericValidation {
  min: number;
  max: number;
  errorMessage: string;
}

export interface QuestionConfig {
  id: string;
  block: 1 | 2 | 3 | 4;
  required: boolean;
  type: QuestionType;
  question: string;
  hint?: string;
  placeholder?: string;
  options?: SelectOption[];
  validation?: NumericValidation;
  defaultValue?: AnswerValue;
}

// ── Question definitions ──────────────────────────────────────────────────────

export const QUESTIONS: QuestionConfig[] = [
  // ── Block 1: Identity & Body Metrics ────────────────────────────────────────
  {
    id: "name",
    block: 1,
    required: true,
    type: "text",
    question: "Как тебя зовут?",
    hint: "Так я буду обращаться к тебе в чате",
    placeholder: "Например: Александр",
  },
  {
    id: "gender",
    block: 1,
    required: true,
    type: "single-select",
    question: "Укажи свой пол",
    hint: "Это влияет на расчёт калорий и программу тренировок",
    options: [
      { value: "male", label: "Мужской" },
      { value: "female", label: "Женский" },
      { value: "prefer_not_to_say", label: "Не указывать" },
    ],
  },
  {
    id: "age",
    block: 1,
    required: true,
    type: "numeric",
    question: "Сколько тебе лет?",
    hint: "Возраст учитывается при расчёте нормы калорий",
    placeholder: "25",
    validation: {
      min: 14,
      max: 99,
      errorMessage: "Укажи возраст от 14 до 99 лет",
    },
  },
  {
    id: "height",
    block: 1,
    required: true,
    type: "numeric",
    question: "Какой у тебя рост? (в сантиметрах)",
    hint: "Нужен для точного расчёта твоей нормы",
    placeholder: "175",
    validation: {
      min: 100,
      max: 250,
      errorMessage: "Укажи рост от 100 до 250 см",
    },
  },
  {
    id: "weight",
    block: 1,
    required: true,
    type: "numeric",
    question: "Какой у тебя вес? (в килограммах)",
    hint: "Данные остаются приватными — нужны только для расчётов",
    placeholder: "70",
    validation: {
      min: 30,
      max: 300,
      errorMessage: "Укажи вес от 30 до 300 кг",
    },
  },
  {
    id: "goal",
    block: 1,
    required: true,
    type: "single-select",
    question: "Какая у тебя главная цель прямо сейчас?",
    hint: "Выбери то, что важнее всего на данный момент",
    options: [
      { value: "lose", label: "Похудеть", description: "Снизить процент жира" },
      {
        value: "gain",
        label: "Набрать массу",
        description: "Увеличить мышечную массу",
      },
      {
        value: "endurance",
        label: "Выносливость",
        description: "Бег, кардио, спорт",
      },
      {
        value: "healthy",
        label: "Оставаться здоровым",
        description: "Поддерживать форму и самочувствие",
      },
      {
        value: "athletic",
        label: "Атлетические результаты",
        description: "Сила, скорость, спортивные показатели",
      },
    ],
  },

  // ── Block 2: Health & Medical ────────────────────────────────────────────────
  {
    id: "conditions",
    block: 2,
    required: true,
    type: "none-or-text",
    question:
      "Есть ли у тебя хронические заболевания или особенности здоровья?",
    hint: "Например: диабет, гипертония, астма. Это важно для безопасной программы",
    placeholder: "Опиши кратко...",
  },
  {
    id: "injuries",
    block: 2,
    required: true,
    type: "none-or-text",
    question: "Есть ли травмы или ограничения, которые влияют на тренировки?",
    hint: "Например: боль в пояснице, проблема с коленом, недавняя операция",
    placeholder: "Опиши кратко...",
  },
  {
    id: "food_allergies",
    block: 2,
    required: true,
    type: "none-or-text",
    question: "Есть ли пищевые аллергии или непереносимость?",
    hint: "Например: лактоза, глютен, орехи, морепродукты",
    placeholder: "Опиши кратко...",
  },

  // ── Block 3: Lifestyle & Nutrition ──────────────────────────────────────────
  {
    id: "meals_per_day",
    block: 3,
    required: false,
    type: "numeric-select",
    question: "Сколько раз в день ты обычно ешь?",
    hint: "Примерно — это поможет нам составить удобный план питания",
    options: [
      { value: "1", label: "1" },
      { value: "2", label: "2" },
      { value: "3", label: "3" },
      { value: "4", label: "4" },
      { value: "5", label: "5" },
      { value: "6", label: "6+" },
    ],
  },
  {
    id: "diet_type",
    block: 3,
    required: false,
    type: "multi-select",
    question: "Как бы ты описал своё питание?",
    hint: "Можно выбрать несколько вариантов",
    options: [
      { value: "omnivore", label: "Всеядный" },
      { value: "vegetarian", label: "Вегетарианец" },
      { value: "vegan", label: "Веган" },
      { value: "keto", label: "Кето" },
      { value: "low_carb", label: "Низкоуглеводное" },
      { value: "mediterranean", label: "Средиземноморское" },
      { value: "none", label: "Без системы" },
    ],
  },
  {
    id: "food_budget",
    block: 3,
    required: false,
    type: "single-select",
    question: "Примерный месячный бюджет на питание?",
    hint: "Поможет подбирать доступные продукты для плана",
    options: [
      {
        value: "under_30000",
        label: "До 30 000 ₸ / мес",
        description: "Только базовые продукты",
      },
      {
        value: "30000_60000",
        label: "30 000 – 60 000 ₸ / мес",
        description: "Стандартный супермаркет",
      },
      {
        value: "60000_120000",
        label: "60 000 – 120 000 ₸ / мес",
        description: "Разнообразное и качественное",
      },
      {
        value: "over_120000",
        label: "Более 120 000 ₸ / мес",
        description: "Премиальные продукты",
      },
    ],
  },

  // ── Block 4: Training Setup ──────────────────────────────────────────────────
  {
    id: "experience_level",
    block: 4,
    required: false,
    type: "single-select",
    question: "Какой у тебя опыт в спорте или фитнесе?",
    hint: "Будь честен — это поможет составить правильный план",
    options: [
      {
        value: "beginner",
        label: "Новичок",
        description: "Почти или совсем не тренировался",
      },
      {
        value: "some",
        label: "Немного",
        description: "Менее 1 года регулярных тренировок",
      },
      { value: "intermediate", label: "Средний", description: "1–3 года" },
      { value: "advanced", label: "Продвинутый", description: "Более 3 лет" },
    ],
  },
  {
    id: "training_location",
    block: 4,
    required: false,
    type: "multi-select",
    question: "Где планируешь тренироваться?",
    hint: "Можно выбрать несколько вариантов",
    options: [
      { value: "home_no_equipment", label: "Дома (без оборудования)" },
      { value: "home_with_equipment", label: "Дома (есть гантели / турник)" },
      { value: "gym", label: "Тренажёрный зал" },
      { value: "outdoors", label: "На улице" },
      { value: "mix", label: "Разные места" },
    ],
  },
  {
    id: "training_days",
    block: 4,
    required: false,
    type: "numeric-select",
    question: "Сколько дней в неделю готов тренироваться?",
    hint: "Выбери реалистичное число, которое сможешь держать",
    options: [
      { value: "1", label: "1" },
      { value: "2", label: "2" },
      { value: "3", label: "3" },
      { value: "4", label: "4" },
      { value: "5", label: "5" },
      { value: "6", label: "6" },
      { value: "7", label: "7" },
    ],
  },
  {
    id: "session_duration",
    block: 4,
    required: false,
    type: "single-select",
    question: "Сколько времени есть на одну тренировку?",
    hint: "Даже 20 минут — уже отличный старт",
    options: [
      { value: "20_30", label: "20–30 минут" },
      { value: "30_45", label: "30–45 минут" },
      { value: "45_60", label: "45–60 минут" },
      { value: "60_90", label: "60–90 минут" },
      { value: "over_90", label: "90+ минут" },
    ],
  },
  {
    id: "training_budget",
    block: 4,
    required: false,
    type: "single-select",
    question: "Месячный бюджет на тренировки?",
    hint: "Это поможет нам учесть доступное оборудование и зал",
    options: [
      {
        value: "no_budget",
        label: "Без бюджета",
        description: "Только упражнения с весом тела",
      },
      {
        value: "under_10000",
        label: "До 10 000 ₸ / мес",
        description: "Базовое домашнее оборудование или улица",
      },
      {
        value: "10000_25000",
        label: "10 000 – 25 000 ₸ / мес",
        description: "Бюджетный зал",
      },
      {
        value: "25000_60000",
        label: "25 000 – 60 000 ₸ / мес",
        description: "Стандартный зал + занятия",
      },
      {
        value: "over_60000",
        label: "Более 60 000 ₸ / мес",
        description: "Премиум зал, тренер или экипировка",
      },
    ],
  },
];

export const BLOCK_LABELS: Record<1 | 2 | 3 | 4, string> = {
  1: "Профиль и параметры",
  2: "Здоровье",
  3: "Питание",
  4: "Тренировки",
};

export const BLOCK_FIRST_INDEX: Record<1 | 2 | 3 | 4, number> = {
  1: 0,
  2: QUESTIONS.findIndex(q => q.block === 2),
  3: QUESTIONS.findIndex(q => q.block === 3),
  4: QUESTIONS.findIndex(q => q.block === 4),
};
