import { useState, useMemo } from "react";
import { useLocation } from "wouter";
import {
  ChevronLeft,
  Sparkles,
  Clock,
  RotateCcw,
  Dumbbell,
  Copy,
  Check,
  RefreshCw,
} from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/_core/hooks/useAuth";
import { trpc } from "@/lib/trpc";

// ── Types ─────────────────────────────────────────────────────────────────────

type Exercise = {
  name: string;
  description: string;
  sets: number;
  reps: string;
  weight: string;
  rest: string;
};

type DayKey =
  | "monday"
  | "tuesday"
  | "wednesday"
  | "thursday"
  | "friday"
  | "saturday"
  | "sunday";

const DAY_LABELS: Record<DayKey, { short: string; full: string }> = {
  monday: { short: "Пон", full: "Понедельник" },
  tuesday: { short: "Вто", full: "Вторник" },
  wednesday: { short: "Сре", full: "Среда" },
  thursday: { short: "Чет", full: "Четверг" },
  friday: { short: "Пят", full: "Пятница" },
  saturday: { short: "Суб", full: "Суббота" },
  sunday: { short: "Вос", full: "Воскресенье" },
};
const DAYS = Object.keys(DAY_LABELS) as DayKey[];

const DAYS_OPTIONS = [3, 4, 5, 6] as const;
const LEVEL_LABELS: Record<string, string> = {
  beginner: "Начинающий",
  intermediate: "Средний",
  advanced: "Продвинутый",
};
const DURATION_WEEKS: Record<string, number> = {
  beginner: 12,
  intermediate: 10,
  advanced: 8,
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function totalExercises(program: Record<string, Exercise[]>): number {
  return Object.values(program).reduce((s, ex) => s + ex.length, 0);
}

function completedExercises(
  done: Set<string>,
  program: Record<string, Exercise[]>
): number {
  return Object.values(program)
    .flat()
    .filter((_, i) => done.has(String(i))).length;
}

// ── Exercise card ─────────────────────────────────────────────────────────────

function ExerciseCard({
  exercise,
  index,
  total,
  done,
  onToggle,
}: {
  exercise: Exercise;
  index: number;
  total: number;
  done: boolean;
  onToggle: () => void;
}) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    const text = `${exercise.name}\n${exercise.sets} подхода × ${exercise.reps} повт.\nВес: ${exercise.weight} | Отдых: ${exercise.rest}`;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div
      className={[
        "rounded-2xl border p-5 transition-all duration-200",
        done
          ? "bg-white/[0.03] border-white/[0.05] opacity-60"
          : "bg-[#13102a] border-white/[0.08] hover:border-purple-500/20",
      ].join(" ")}
    >
      <div className="flex items-start gap-4">
        {/* Checkbox */}
        <button
          onClick={onToggle}
          className={[
            "mt-0.5 w-5 h-5 rounded-full border-2 flex-shrink-0 flex items-center justify-center transition-all duration-200",
            done
              ? "bg-purple-600 border-purple-600"
              : "border-white/20 hover:border-purple-400/60",
          ].join(" ")}
        >
          {done && <Check size={10} className="text-white" strokeWidth={3} />}
        </button>

        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3
                className={[
                  "text-base font-semibold leading-snug",
                  done ? "line-through text-white/40" : "text-white",
                ].join(" ")}
              >
                {exercise.name}
              </h3>
              {exercise.description && (
                <p className="text-sm text-white/40 mt-0.5 leading-relaxed">
                  {exercise.description}
                </p>
              )}
            </div>
            <button
              onClick={handleCopy}
              title="Копировать"
              className="w-8 h-8 rounded-lg bg-white/[0.04] border border-white/[0.07] flex items-center justify-center text-white/30 hover:text-white/70 hover:bg-white/[0.08] flex-shrink-0 transition-all"
            >
              {copied ? (
                <Check size={13} className="text-green-400" />
              ) : (
                <Copy size={13} />
              )}
            </button>
          </div>

          {/* Stats grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-4">
            <StatPill label="Подходы" value={String(exercise.sets)} />
            <StatPill label="Повторения" value={exercise.reps} />
            <StatPill
              label="Вес"
              value={exercise.weight}
              icon={<Dumbbell size={11} />}
            />
            <StatPill
              label="Отдых"
              value={exercise.rest}
              icon={<Clock size={11} />}
            />
          </div>

          <p className="text-[11px] text-white/25 mt-3">
            Упражнение {index + 1} из {total}
          </p>
        </div>
      </div>
    </div>
  );
}

function StatPill({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="bg-white/[0.04] border border-white/[0.07] rounded-xl px-3 py-2.5">
      <p className="text-[10px] text-white/35 mb-0.5 flex items-center gap-1">
        {icon}
        {label}
      </p>
      <p className="text-sm font-bold text-white">{value}</p>
    </div>
  );
}

// ── Generate modal ────────────────────────────────────────────────────────────

function GenerateModal({
  open,
  onClose,
  onGenerate,
  isLoading,
}: {
  open: boolean;
  onClose: () => void;
  onGenerate: (days: number) => void;
  isLoading: boolean;
}) {
  const [days, setDays] = useState(3);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative w-full max-w-sm bg-[#13102a] border border-white/[0.10] rounded-2xl p-6 shadow-2xl">
        <h2 className="text-lg font-bold text-white mb-1">
          Сгенерировать план
        </h2>
        <p className="text-xs text-white/40 mb-5">
          ИИ составит план на основе вашего профиля, целей и уровня.
        </p>

        <label className="block text-sm text-white/60 mb-2">
          Тренировочных дней в неделю
        </label>
        <div className="flex gap-2 mb-6">
          {DAYS_OPTIONS.map(d => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={[
                "flex-1 py-2.5 rounded-xl text-sm font-semibold border transition-all",
                days === d
                  ? "bg-purple-600/30 border-purple-500/50 text-purple-200"
                  : "bg-white/[0.03] border-white/[0.08] text-white/50 hover:text-white hover:bg-white/[0.07]",
              ].join(" ")}
            >
              {d}×
            </button>
          ))}
        </div>

        <button
          onClick={() => onGenerate(days)}
          disabled={isLoading}
          className="w-full flex items-center justify-center gap-2 py-3 rounded-2xl bg-purple-600 hover:bg-purple-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm shadow-[0_4px_20px_rgba(168,85,247,0.4)] transition-all"
        >
          {isLoading ? (
            <>
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Генерирую...
            </>
          ) : (
            <>
              <Sparkles size={16} />
              Сгенерировать
            </>
          )}
        </button>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function WorkoutPlan() {
  const { user, isAuthenticated, loading } = useAuth();
  const [, navigate] = useLocation();
  const [activeDay, setActiveDay] = useState<DayKey>("monday");
  const [showModal, setShowModal] = useState(false);
  const [doneKeys, setDoneKeys] = useState<Set<string>>(new Set());

  const utils = trpc.useUtils();

  const profileQuery = trpc.profile.get.useQuery(undefined, {
    enabled: isAuthenticated,
    retry: false,
  });

  useEffect(() => {
    if (!loading && !isAuthenticated) navigate("/");
  }, [loading, isAuthenticated, navigate]);

  useEffect(() => {
    if (profileQuery.data && !profileQuery.data.onboarding_completed)
      navigate("/onboarding");
  }, [profileQuery.data, navigate]);

  const programQuery = trpc.workout.getActive.useQuery(undefined, {
    enabled: isAuthenticated,
    retry: false,
  });

  const generateMutation = trpc.workout.generate.useMutation({
    onSuccess: () => {
      toast.success("План тренировок создан!");
      setShowModal(false);
      setDoneKeys(new Set());
      utils.workout.getActive.invalidate();
    },
    onError: err => toast.error(err.message || "Ошибка генерации"),
  });

  const program = programQuery.data;
  const days: Record<DayKey, Exercise[]> = useMemo(() => {
    const fallback = DAYS.reduce(
      (acc, d) => ({ ...acc, [d]: [] }),
      {} as Record<DayKey, Exercise[]>
    );
    if (!program?.program) return fallback;
    return DAYS.reduce(
      (acc, d) => ({ ...acc, [d]: (program.program![d] ?? []) as Exercise[] }),
      {} as Record<DayKey, Exercise[]>
    );
  }, [program]);

  const total = useMemo(() => totalExercises(days), [days]);
  const level = program?.level ?? "beginner";
  const levelLabel =
    program?.level_label ?? LEVEL_LABELS[level] ?? "Начинающий";
  const durationWeeks = DURATION_WEEKS[level] ?? 12;

  const dayExercises = days[activeDay] ?? [];

  function toggleDone(day: DayKey, idx: number) {
    const key = `${day}-${idx}`;
    setDoneKeys(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }

  const doneCount = useMemo(
    () =>
      DAYS.reduce(
        (sum, d) =>
          sum + days[d].filter((_, i) => doneKeys.has(`${d}-${i}`)).length,
        0
      ),
    [doneKeys, days]
  );

  const progress = total > 0 ? Math.round((doneCount / total) * 100) : 0;

  if (loading || !isAuthenticated) return null;

  return (
    <div className="min-h-screen bg-[#0b0817] relative overflow-hidden flex flex-col">
      {/* Ambient background */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none select-none">
        <div className="absolute -top-60 right-0 w-[600px] h-[600px] bg-purple-700 rounded-full blur-[160px] opacity-[0.08]" />
        <div className="absolute top-1/2 -left-60 w-[500px] h-[500px] bg-indigo-600 rounded-full blur-[140px] opacity-[0.06]" />
        <div className="absolute -bottom-60 right-1/4 w-[500px] h-[500px] bg-violet-800 rounded-full blur-[150px] opacity-[0.05]" />
      </div>

      {/* Header */}
      <header className="relative z-10 w-full border-b border-white/[0.05] bg-[#0b0817]/80 backdrop-blur-md sticky top-0">
        <div className="max-w-4xl mx-auto px-4 md:px-8 py-4 flex items-center gap-4">
          <button
            onClick={() => navigate("/dashboard")}
            className="w-9 h-9 rounded-xl bg-white/[0.05] border border-white/[0.08] hover:bg-white/[0.09] flex items-center justify-center text-white/50 hover:text-white transition-all"
          >
            <ChevronLeft size={18} />
          </button>

          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-purple-500/30 to-violet-600/20 border border-purple-500/25 flex items-center justify-center flex-shrink-0">
            <Dumbbell size={16} className="text-purple-300" />
          </div>

          <div className="flex-1">
            <h1 className="text-base font-bold text-white">Мой план</h1>
            <p className="text-[11px] text-white/30">Тренировка</p>
          </div>

          {user?.name && (
            <span className="text-sm text-white/40 hidden md:block">
              {user.name}
            </span>
          )}

          {program && (
            <button
              onClick={() => setShowModal(true)}
              title="Перегенерировать план"
              className="w-9 h-9 rounded-xl bg-white/[0.05] border border-white/[0.08] hover:bg-purple-500/10 hover:border-purple-500/30 flex items-center justify-center text-white/40 hover:text-purple-300 transition-all"
            >
              <RefreshCw size={15} />
            </button>
          )}
        </div>
      </header>

      <main className="relative z-10 flex-1 max-w-4xl mx-auto w-full px-4 md:px-8 py-6 space-y-6">
        {/* Loading */}
        {programQuery.isLoading && (
          <div className="space-y-4">
            <div className="h-44 rounded-3xl bg-white/[0.04] animate-pulse border border-white/[0.06]" />
            <div className="h-16 rounded-2xl bg-white/[0.03] animate-pulse border border-white/[0.05]" />
          </div>
        )}

        {/* Empty state */}
        {!programQuery.isLoading && !program && (
          <div className="flex flex-col items-center gap-6 py-20 text-center">
            <div className="relative">
              <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-purple-500/20 to-violet-600/10 border border-purple-500/20 flex items-center justify-center">
                <Dumbbell size={32} className="text-purple-300" />
              </div>
              <div className="absolute inset-0 rounded-2xl blur-xl bg-purple-500/10" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white mb-2">
                Нет плана тренировок
              </h2>
              <p className="text-sm text-white/35 max-w-xs leading-relaxed">
                Пусть ИИ составит персональный план на основе ваших целей и
                уровня подготовки
              </p>
            </div>
            <button
              onClick={() => setShowModal(true)}
              className="flex items-center gap-2.5 px-6 py-3 rounded-2xl bg-purple-600 hover:bg-purple-500 border border-purple-500/50 text-white font-semibold text-sm shadow-[0_4px_20px_rgba(168,85,247,0.4)] hover:shadow-[0_4px_28px_rgba(168,85,247,0.55)] transition-all active:scale-[0.97]"
            >
              <Sparkles size={16} />
              Сгенерировать план
            </button>
          </div>
        )}

        {/* Program view */}
        {program && (
          <>
            {/* Hero card */}
            <div className="rounded-3xl bg-gradient-to-br from-[#1a1035] via-[#16112e] to-[#120d28] border border-white/[0.07] p-6 md:p-8">
              <div className="flex flex-col md:flex-row md:items-start gap-4">
                <div className="flex-1">
                  <h2 className="text-2xl md:text-3xl font-bold text-white leading-tight mb-2">
                    {program.name}
                  </h2>
                  <p className="text-sm text-white/40 leading-relaxed max-w-lg">
                    Персональный план тренировок, составленный ИИ на основе
                    ваших целей и уровня подготовки.
                  </p>
                </div>
                <div className="flex flex-row md:flex-col gap-2 flex-shrink-0">
                  <div className="px-4 py-2 rounded-xl bg-white/[0.06] border border-white/[0.09] text-center">
                    <p className="text-[10px] text-white/35 mb-0.5">
                      Сложность
                    </p>
                    <p className="text-sm font-bold text-white">{levelLabel}</p>
                  </div>
                  <div className="px-4 py-2 rounded-xl bg-white/[0.06] border border-white/[0.09] text-center">
                    <p className="text-[10px] text-white/35 mb-0.5">
                      Длительность
                    </p>
                    <p className="text-sm font-bold text-white">
                      {durationWeeks} недель
                    </p>
                  </div>
                </div>
              </div>

              {/* Progress bar */}
              <div className="mt-6">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-white/35">Прогресс</span>
                  <span className="text-xs text-white/35">
                    {doneCount} из {total}
                  </span>
                </div>
                <div className="h-2 rounded-full bg-white/[0.06] overflow-hidden">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-purple-600 to-violet-500 transition-all duration-500"
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>
            </div>

            {/* Day tabs */}
            <div className="grid grid-cols-7 gap-1.5">
              {DAYS.map(day => {
                const count = days[day].length;
                const isActive = activeDay === day;
                const doneInDay = days[day].filter((_, i) =>
                  doneKeys.has(`${day}-${i}`)
                ).length;
                return (
                  <button
                    key={day}
                    onClick={() => setActiveDay(day)}
                    className={[
                      "flex flex-col items-center py-3 px-1 rounded-2xl border transition-all duration-200",
                      isActive
                        ? "bg-gradient-to-b from-purple-600/30 to-violet-600/20 border-purple-500/40 shadow-[0_2px_12px_rgba(168,85,247,0.2)]"
                        : count > 0
                          ? "bg-white/[0.04] border-white/[0.07] hover:bg-white/[0.07] hover:border-white/[0.12]"
                          : "bg-white/[0.02] border-white/[0.04] hover:bg-white/[0.04]",
                    ].join(" ")}
                  >
                    <span
                      className={[
                        "text-[10px] font-medium mb-1",
                        isActive ? "text-purple-200" : "text-white/40",
                      ].join(" ")}
                    >
                      {DAY_LABELS[day].short}
                    </span>
                    <span
                      className={[
                        "text-base font-bold",
                        isActive
                          ? "text-white"
                          : count > 0
                            ? "text-white/80"
                            : "text-white/20",
                      ].join(" ")}
                    >
                      {count}
                    </span>
                    {count > 0 && doneInDay === count && (
                      <div className="w-1 h-1 rounded-full bg-green-400 mt-1" />
                    )}
                  </button>
                );
              })}
            </div>

            {/* Day title */}
            <div className="flex items-center justify-between">
              <h2 className="text-2xl font-bold text-white">
                {DAY_LABELS[activeDay].full}
              </h2>
              {dayExercises.length > 0 && (
                <span className="text-xs text-white/30">
                  {
                    dayExercises.filter((_, i) =>
                      doneKeys.has(`${activeDay}-${i}`)
                    ).length
                  }{" "}
                  / {dayExercises.length} выполнено
                </span>
              )}
            </div>

            {/* Exercises */}
            {dayExercises.length === 0 ? (
              <div className="flex flex-col items-center gap-3 py-12 text-center">
                <div className="w-12 h-12 rounded-2xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-center">
                  <RotateCcw size={18} className="text-white/20" />
                </div>
                <p className="text-sm text-white/30">
                  День отдыха — восстановление
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {dayExercises.map((ex, i) => (
                  <ExerciseCard
                    key={i}
                    exercise={ex}
                    index={i}
                    total={dayExercises.length}
                    done={doneKeys.has(`${activeDay}-${i}`)}
                    onToggle={() => toggleDone(activeDay, i)}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </main>

      <GenerateModal
        open={showModal}
        onClose={() => setShowModal(false)}
        onGenerate={days => generateMutation.mutate({ days_per_week: days })}
        isLoading={generateMutation.isPending}
      />
    </div>
  );
}
