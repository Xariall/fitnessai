import { useReducer, useCallback } from "react";
import { useLocation } from "wouter";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight, SkipForward } from "lucide-react";
import { trpc } from "@/lib/trpc";
import {
  QUESTIONS,
  BLOCK_LABELS,
  BLOCK_FIRST_INDEX,
} from "@/data/onboardingQuestions";
import { QuestionCard } from "./QuestionCard";
import type {
  AnswerValue,
  OnboardingPayload,
  Gender,
  Goal,
  ExperienceLevel,
  SessionDuration,
  TrainingBudget,
  FoodBudget,
} from "@/types/userProfile";

// ── Reducer ───────────────────────────────────────────────────────────────────

interface OnboardingState {
  currentIndex: number;
  answers: Record<string, AnswerValue>;
  errors: Record<string, string>;
}

type OnboardingAction =
  | { type: "SET_ANSWER"; questionId: string; value: AnswerValue }
  | { type: "SET_ERROR"; questionId: string; error: string }
  | { type: "CLEAR_ERROR"; questionId: string }
  | { type: "GO_TO"; index: number };

function reducer(
  state: OnboardingState,
  action: OnboardingAction
): OnboardingState {
  switch (action.type) {
    case "SET_ANSWER":
      return {
        ...state,
        answers: { ...state.answers, [action.questionId]: action.value },
        errors: { ...state.errors, [action.questionId]: "" },
      };
    case "SET_ERROR":
      return {
        ...state,
        errors: { ...state.errors, [action.questionId]: action.error },
      };
    case "CLEAR_ERROR":
      return { ...state, errors: { ...state.errors, [action.questionId]: "" } };
    case "GO_TO":
      return { ...state, currentIndex: action.index, errors: {} };
    default:
      return state;
  }
}

// ── Validation helpers ────────────────────────────────────────────────────────

function validate(
  questionId: string,
  value: AnswerValue,
  questions = QUESTIONS
): string {
  const q = questions.find(q => q.id === questionId);
  if (!q) return "";

  if (q.required) {
    if (value === null || value === undefined)
      return "Пожалуйста, ответь на этот вопрос";
    if (typeof value === "string" && value.trim() === "")
      return "Пожалуйста, ответь на этот вопрос";
    if (Array.isArray(value) && value.length === 0)
      return "Выбери хотя бы один вариант";
  }

  if (q.type === "numeric" && q.validation && value !== null) {
    const n = Number(value);
    if (isNaN(n) || n < q.validation.min || n > q.validation.max) {
      return q.validation.errorMessage;
    }
  }

  return "";
}

// ── Payload builder ───────────────────────────────────────────────────────────

function buildPayload(answers: Record<string, AnswerValue>): OnboardingPayload {
  const str = (id: string) => {
    const v = answers[id];
    return v !== null && v !== undefined ? String(v).trim() : "";
  };
  const num = (id: string) => {
    const v = answers[id];
    return v !== null && v !== undefined ? Number(v) : undefined;
  };
  const multiStr = (id: string) => {
    const v = answers[id];
    return Array.isArray(v) ? v.join(",") : undefined;
  };

  return {
    name: str("name"),
    gender: str("gender") as Gender,
    age: Number(answers["age"]),
    height: Number(answers["height"]),
    weight: Number(answers["weight"]),
    goal: str("goal") as Goal,
    conditions: str("conditions") || "none",
    injuries: str("injuries") || "none",
    food_allergies: str("food_allergies") || "none",
    meals_per_day: num("meals_per_day"),
    diet_type: multiStr("diet_type"),
    food_budget: (str("food_budget") || undefined) as FoodBudget | undefined,
    experience_level: (str("experience_level") || undefined) as
      | ExperienceLevel
      | undefined,
    training_location: multiStr("training_location"),
    training_days: num("training_days"),
    session_duration: (str("session_duration") || undefined) as
      | SessionDuration
      | undefined,
    training_budget: (str("training_budget") || undefined) as
      | TrainingBudget
      | undefined,
  };
}

// ── Component ─────────────────────────────────────────────────────────────────

interface OnboardingFlowProps {
  initialName?: string;
}

export function OnboardingFlow({ initialName }: OnboardingFlowProps) {
  const [, navigate] = useLocation();

  const [state, dispatch] = useReducer(reducer, {
    currentIndex: 0,
    answers: initialName ? { name: initialName } : {},
    errors: {},
  });

  const submitMutation = trpc.profile.submitOnboarding.useMutation({
    onSuccess: () => navigate("/dashboard"),
    onError: () => toast.error("Ошибка сохранения. Попробуй ещё раз."),
  });

  const currentQuestion = QUESTIONS[state.currentIndex];
  const totalQuestions = QUESTIONS.length;
  const progress = Math.round((state.currentIndex / totalQuestions) * 100);

  const currentBlock = currentQuestion.block as 1 | 2 | 3 | 4;
  const isFirstOfBlock = state.currentIndex === BLOCK_FIRST_INDEX[currentBlock];
  const isOptionalBlock = currentBlock === 3 || currentBlock === 4;
  const isLast = state.currentIndex === totalQuestions - 1;

  const currentValue = state.answers[currentQuestion.id] ?? null;
  const currentError = state.errors[currentQuestion.id] ?? "";

  const handleChange = useCallback(
    (value: AnswerValue) => {
      dispatch({ type: "SET_ANSWER", questionId: currentQuestion.id, value });
    },
    [currentQuestion.id]
  );

  const handleNext = () => {
    const err = validate(currentQuestion.id, currentValue);
    if (err) {
      dispatch({
        type: "SET_ERROR",
        questionId: currentQuestion.id,
        error: err,
      });
      return;
    }

    if (isLast) {
      submitMutation.mutate(buildPayload(state.answers));
      return;
    }

    dispatch({ type: "GO_TO", index: state.currentIndex + 1 });
  };

  const handleBack = () => {
    if (state.currentIndex > 0) {
      dispatch({ type: "GO_TO", index: state.currentIndex - 1 });
    }
  };

  const handleSkipBlock = () => {
    // Find the first question of the next block, or submit if no next block
    const nextBlockIndex = QUESTIONS.findIndex(
      (q, i) => i > state.currentIndex && q.block > currentBlock
    );
    if (nextBlockIndex !== -1) {
      dispatch({ type: "GO_TO", index: nextBlockIndex });
    } else {
      // No more blocks — submit with what we have
      submitMutation.mutate(buildPayload(state.answers));
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (
      e.key === "Enter" &&
      currentQuestion.type !== "text" &&
      currentQuestion.type !== "none-or-text"
    ) {
      handleNext();
    }
  };

  return (
    <div onKeyDown={handleKeyDown} className="w-full max-w-lg">
      {/* Progress bar */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-white/40 uppercase tracking-wider">
            {BLOCK_LABELS[currentBlock]}
          </span>
          <span className="text-xs text-white/40">
            {state.currentIndex + 1} / {totalQuestions}
          </span>
        </div>
        <div className="w-full h-1 bg-white/10 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-purple-500 to-cyan-500 rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
            role="progressbar"
            aria-valuenow={progress}
            aria-valuemin={0}
            aria-valuemax={100}
          />
        </div>
      </div>

      {/* Card */}
      <div className="glass p-8 rounded-2xl border border-white/10">
        <div className="space-y-6">
          {/* Question */}
          <div>
            <h2 className="text-xl font-bold text-white mb-1 leading-snug">
              {currentQuestion.question}
            </h2>
            {currentQuestion.hint && (
              <p className="text-sm text-white/50">{currentQuestion.hint}</p>
            )}
          </div>

          {/* Input */}
          <QuestionCard
            question={currentQuestion}
            value={currentValue}
            onChange={handleChange}
            error={currentError}
          />
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-between mt-8">
          <button
            type="button"
            onClick={handleBack}
            aria-label="Назад"
            className={`flex items-center gap-1 text-sm text-white/50 hover:text-white transition-colors ${
              state.currentIndex === 0 ? "invisible" : ""
            }`}
          >
            <ChevronLeft size={16} /> Назад
          </button>

          <div className="flex items-center gap-3">
            {isOptionalBlock && isFirstOfBlock && (
              <button
                type="button"
                onClick={handleSkipBlock}
                aria-label="Пропустить блок"
                className="flex items-center gap-1 text-sm text-white/40 hover:text-white/70 transition-colors"
              >
                <SkipForward size={14} />
                Пропустить
              </button>
            )}

            <button
              type="button"
              onClick={handleNext}
              disabled={submitMutation.isPending}
              aria-label={isLast ? "Завершить" : "Далее"}
              className="btn-primary flex items-center gap-1 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {submitMutation.isPending
                ? "Сохранение..."
                : isLast
                  ? "Готово!"
                  : "Далее"}
              {!submitMutation.isPending && <ChevronRight size={16} />}
            </button>
          </div>
        </div>
      </div>

      {/* Optional hint */}
      {isOptionalBlock && (
        <p className="text-center text-white/20 text-xs mt-4">
          Не уверен? Не беда — можно обновить позже в профиле.
        </p>
      )}
    </div>
  );
}
