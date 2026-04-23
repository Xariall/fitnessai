// ── Constrained field types ───────────────────────────────────────────────────

export type Gender = "male" | "female" | "prefer_not_to_say";

export type Goal =
  | "lose"
  | "gain"
  | "maintain"
  | "recomposition"
  | "endurance"
  | "healthy"
  | "athletic";

export type ActivityLevel = "sedentary" | "moderate" | "active" | "athlete";

export type ExperienceLevel = "beginner" | "some" | "intermediate" | "advanced";

export type DietType =
  | "omnivore"
  | "vegetarian"
  | "vegan"
  | "keto"
  | "low_carb"
  | "mediterranean"
  | "none";

export type TrainingLocation =
  | "home_no_equipment"
  | "home_with_equipment"
  | "gym"
  | "outdoors"
  | "mix";

export type FoodBudget =
  | "under_5000"
  | "5000_10000"
  | "10000_20000"
  | "over_20000";

export type TrainingBudget =
  | "no_budget"
  | "under_2000"
  | "2000_5000"
  | "5000_15000"
  | "over_15000";

export type SessionDuration = "20_30" | "30_45" | "45_60" | "60_90" | "over_90";

// ── Full user profile ─────────────────────────────────────────────────────────

export interface UserProfile {
  id: number;
  email: string | null;
  name: string | null;
  picture: string | null;
  // Block 1
  gender: Gender | null;
  age: number | null;
  height: number | null;
  weight: number | null;
  goal: Goal | null;
  activity: ActivityLevel | null;
  // Block 2
  injuries: string | null;
  conditions: string | null;
  food_allergies: string | null;
  // Block 3
  meals_per_day: number | null;
  diet_type: string | null;
  food_budget: FoodBudget | null;
  // Block 4
  experience_level: ExperienceLevel | null;
  training_location: string | null;
  training_days: number | null;
  session_duration: SessionDuration | null;
  training_budget: TrainingBudget | null;
  // Flags
  onboarding_completed: boolean;
  nutrition_unlocked: boolean;
  workout_unlocked: boolean;
}

// ── Onboarding answers (flat keyed record) ────────────────────────────────────

export type AnswerValue = string | number | string[] | null;

export type OnboardingAnswers = Record<string, AnswerValue>;

// ── Onboarding submission payload ─────────────────────────────────────────────

export interface OnboardingPayload {
  // Block 1 — required
  name: string;
  gender: Gender;
  age: number;
  height: number;
  weight: number;
  goal: Goal;
  // Block 2 — required
  conditions: string;
  injuries: string;
  food_allergies: string;
  // Block 3 — optional
  meals_per_day?: number;
  diet_type?: string;
  food_budget?: FoodBudget;
  // Block 4 — optional
  experience_level?: ExperienceLevel;
  training_location?: string;
  training_days?: number;
  session_duration?: SessionDuration;
  training_budget?: TrainingBudget;
}
