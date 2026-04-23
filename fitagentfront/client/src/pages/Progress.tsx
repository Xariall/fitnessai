import { useState, useMemo, useEffect } from "react";
import { useLocation } from "wouter";
import {
  ChevronLeft,
  TrendingUp,
  TrendingDown,
  Minus,
  Scale,
  Dumbbell,
  Target,
  Activity,
  Plus,
  Check,
} from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/_core/hooks/useAuth";
import { trpc } from "@/lib/trpc";

// ── Constants ─────────────────────────────────────────────────────────────────

const GOAL_LABELS: Record<string, string> = {
  weight_loss: "Похудение",
  muscle_gain: "Набор массы",
  maintenance: "Поддержание формы",
  endurance: "Выносливость",
  strength: "Сила",
};

const ACTIVITY_LABELS: Record<string, string> = {
  sedentary: "Малоподвижный",
  light: "Лёгкая активность",
  moderate: "Умеренная активность",
  active: "Высокая активность",
  very_active: "Очень высокая",
};

// ── Mini weight chart ─────────────────────────────────────────────────────────

function WeightChart({
  data,
}: {
  data: Array<{ weight: number; logged_at: string }>;
}) {
  const reversed = [...data].reverse(); // chronological order
  if (reversed.length < 2) {
    return (
      <div className="h-28 flex items-center justify-center">
        <p className="text-xs text-white/25">Недостаточно данных для графика</p>
      </div>
    );
  }

  const weights = reversed.map(d => d.weight);
  const min = Math.min(...weights) - 0.5;
  const max = Math.max(...weights) + 0.5;
  const range = max - min || 1;

  const W = 400;
  const H = 100;
  const pad = 8;

  const points = reversed.map((d, i) => {
    const x = pad + (i / (reversed.length - 1)) * (W - pad * 2);
    const y = H - pad - ((d.weight - min) / range) * (H - pad * 2);
    return { x, y, ...d };
  });

  const path = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`)
    .join(" ");

  const areaPath = `${path} L ${points[points.length - 1].x} ${H} L ${points[0].x} ${H} Z`;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full h-28"
      preserveAspectRatio="none"
    >
      <defs>
        <linearGradient id="wg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#a855f7" stopOpacity="0.3" />
          <stop offset="100%" stopColor="#a855f7" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill="url(#wg)" />
      <path
        d={path}
        fill="none"
        stroke="#a855f7"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {points.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r="3" fill="#a855f7" />
      ))}
    </svg>
  );
}

// ── Log weight modal ──────────────────────────────────────────────────────────

function LogWeightModal({
  current,
  onLog,
  isLoading,
  onClose,
}: {
  current: number | null;
  onLog: (w: number) => void;
  isLoading: boolean;
  onClose: () => void;
}) {
  const [value, setValue] = useState(current ? String(current) : "");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const n = parseFloat(value);
    if (isNaN(n) || n <= 0 || n > 500) return;
    onLog(n);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative w-full max-w-xs bg-[#13102a] border border-white/[0.10] rounded-2xl p-6 shadow-2xl">
        <h2 className="text-base font-bold text-white mb-4">Записать вес</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-xs text-white/40 mb-1.5 block">
              Вес (кг)
            </label>
            <input
              autoFocus
              type="number"
              step="0.1"
              min="20"
              max="500"
              value={value}
              onChange={e => setValue(e.target.value)}
              placeholder="70.5"
              className="w-full bg-white/[0.04] border border-white/[0.10] rounded-xl px-4 py-3 text-white text-lg font-bold text-center placeholder:text-white/20 focus:outline-none focus:border-purple-500/60 transition-colors"
            />
          </div>
          <button
            type="submit"
            disabled={isLoading || !value}
            className="w-full py-3 rounded-xl bg-purple-600 hover:bg-purple-500 disabled:opacity-40 text-white font-semibold text-sm flex items-center justify-center gap-2 transition-all"
          >
            {isLoading ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <>
                <Check size={15} />
                Сохранить
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  accent,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  sub?: string;
  accent: string;
}) {
  return (
    <div className={`rounded-2xl border p-4 bg-gradient-to-br ${accent}`}>
      <div className="flex items-start justify-between mb-3">
        <p className="text-xs text-white/40 font-medium">{label}</p>
        <Icon size={16} className="text-white/30" />
      </div>
      <p className="text-2xl font-bold text-white">{value}</p>
      {sub && <p className="text-xs text-white/35 mt-1">{sub}</p>}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Progress() {
  const { isAuthenticated, loading } = useAuth();
  const [, navigate] = useLocation();
  const [showLogModal, setShowLogModal] = useState(false);

  const utils = trpc.useUtils();

  const profileQuery = trpc.profile.get.useQuery(undefined, { enabled: isAuthenticated, retry: false });

  useEffect(() => {
    if (!loading && !isAuthenticated) navigate("/");
  }, [loading, isAuthenticated, navigate]);

  useEffect(() => {
    if (profileQuery.data && !profileQuery.data.onboarding_completed) navigate("/chat");
  }, [profileQuery.data, navigate]);

  const summaryQuery = trpc.progress.getSummary.useQuery(undefined, {
    enabled: isAuthenticated,
    retry: false,
  });

  const logWeightMutation = trpc.progress.logWeight.useMutation({
    onSuccess: () => {
      toast.success("Вес записан!");
      setShowLogModal(false);
      utils.progress.getSummary.invalidate();
    },
    onError: () => toast.error("Не удалось сохранить вес"),
  });

  const data = summaryQuery.data;

  const weightTrend = useMemo(() => {
    if (data?.weight_change_90d == null) return null;
    if (data.weight_change_90d > 0.2) return "up";
    if (data.weight_change_90d < -0.2) return "down";
    return "stable";
  }, [data]);

  const TrendIcon =
    weightTrend === "up"
      ? TrendingUp
      : weightTrend === "down"
        ? TrendingDown
        : Minus;

  const trendColor =
    weightTrend === "up"
      ? "text-orange-400"
      : weightTrend === "down"
        ? "text-emerald-400"
        : "text-white/40";

  if (loading || !isAuthenticated) return null;

  return (
    <div className="min-h-screen bg-[#0b0817] relative overflow-hidden flex flex-col">
      {/* Ambient */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none select-none">
        <div className="absolute -top-60 -right-40 w-[500px] h-[500px] bg-orange-700 rounded-full blur-[160px] opacity-[0.06]" />
        <div className="absolute top-1/2 -left-60 w-[450px] h-[450px] bg-purple-700 rounded-full blur-[140px] opacity-[0.06]" />
        <div className="absolute -bottom-40 right-1/3 w-[400px] h-[400px] bg-indigo-700 rounded-full blur-[120px] opacity-[0.05]" />
      </div>

      {/* Header */}
      <header className="relative z-10 w-full border-b border-white/[0.05] bg-[#0b0817]/80 backdrop-blur-md sticky top-0">
        <div className="max-w-3xl mx-auto px-4 md:px-6 py-4 flex items-center gap-3">
          <button
            onClick={() => navigate("/dashboard")}
            className="w-9 h-9 rounded-xl bg-white/[0.05] border border-white/[0.08] hover:bg-white/[0.09] flex items-center justify-center text-white/50 hover:text-white transition-all"
          >
            <ChevronLeft size={18} />
          </button>

          <div className="flex-1">
            <h1 className="text-base font-bold text-white">Мой прогресс</h1>
            {data && (
              <p className="text-[11px] text-white/30 mt-0.5">
                {data.total_workouts} тренировок записано
              </p>
            )}
          </div>

          <button
            onClick={() => setShowLogModal(true)}
            title="Записать вес"
            className="w-9 h-9 rounded-xl bg-purple-600/20 border border-purple-500/30 hover:bg-purple-600/30 flex items-center justify-center text-purple-300 transition-all"
          >
            <Plus size={16} />
          </button>
        </div>
      </header>

      {/* Main */}
      <main className="relative z-10 flex-1 max-w-3xl mx-auto w-full px-4 md:px-6 py-6 space-y-6">
        {/* Loading */}
        {summaryQuery.isLoading && (
          <div className="space-y-4">
            {[1, 2, 3].map(i => (
              <div
                key={i}
                className="h-24 rounded-2xl bg-white/[0.04] animate-pulse border border-white/[0.05]"
              />
            ))}
          </div>
        )}

        {data && (
          <>
            {/* Stats grid */}
            <div className="grid grid-cols-2 gap-3">
              <StatCard
                icon={Scale}
                label="Текущий вес"
                value={
                  data.current_weight != null
                    ? `${data.current_weight} кг`
                    : "—"
                }
                sub={
                  data.weight_change_90d != null
                    ? `за 90 дней: ${data.weight_change_90d > 0 ? "+" : ""}${data.weight_change_90d} кг`
                    : "нет данных"
                }
                accent="from-purple-500/10 to-purple-600/5 border-purple-500/20"
              />
              <StatCard
                icon={Dumbbell}
                label="Тренировок"
                value={String(data.total_workouts)}
                sub="всего записано"
                accent="from-cyan-500/10 to-cyan-600/5 border-cyan-500/20"
              />
              <StatCard
                icon={Target}
                label="Цель"
                value={GOAL_LABELS[data.profile.goal ?? ""] ?? "—"}
                accent="from-orange-500/10 to-orange-600/5 border-orange-500/20"
              />
              <StatCard
                icon={Activity}
                label="Активность"
                value={ACTIVITY_LABELS[data.profile.activity ?? ""] ?? "—"}
                accent="from-emerald-500/10 to-emerald-600/5 border-emerald-500/20"
              />
            </div>

            {/* Weight chart */}
            <div className="rounded-2xl bg-white/[0.03] border border-white/[0.07] p-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <p className="text-sm font-semibold text-white">
                    Динамика веса
                  </p>
                  <p className="text-xs text-white/30 mt-0.5">
                    последние 90 дней
                  </p>
                </div>
                {data.weight_change_90d != null && (
                  <div
                    className={`flex items-center gap-1 text-sm font-semibold ${trendColor}`}
                  >
                    <TrendIcon size={15} />
                    {data.weight_change_90d > 0 ? "+" : ""}
                    {data.weight_change_90d} кг
                  </div>
                )}
              </div>

              {data.weight_history.length === 0 ? (
                <div className="h-28 flex flex-col items-center justify-center gap-3">
                  <Scale size={28} className="text-white/15" />
                  <p className="text-xs text-white/30">Нет записей веса</p>
                  <button
                    onClick={() => setShowLogModal(true)}
                    className="text-xs text-purple-400 hover:text-purple-300 transition-colors"
                  >
                    Записать сейчас →
                  </button>
                </div>
              ) : (
                <WeightChart data={data.weight_history} />
              )}

              {data.weight_history.length > 0 && (
                <div className="mt-3 pt-3 border-t border-white/[0.05] flex items-center justify-between">
                  <p className="text-xs text-white/30">
                    Последняя запись:{" "}
                    {new Date(
                      data.weight_history[0].logged_at
                    ).toLocaleDateString("ru-RU", {
                      day: "numeric",
                      month: "short",
                    })}
                  </p>
                  <button
                    onClick={() => setShowLogModal(true)}
                    className="text-xs text-purple-400 hover:text-purple-300 flex items-center gap-1 transition-colors"
                  >
                    <Plus size={12} />
                    Добавить
                  </button>
                </div>
              )}
            </div>

            {/* Recent workouts */}
            <div className="rounded-2xl bg-white/[0.03] border border-white/[0.07] p-5">
              <p className="text-sm font-semibold text-white mb-4">
                Последние тренировки
              </p>

              {data.recent_workouts.length === 0 ? (
                <div className="flex flex-col items-center gap-3 py-8">
                  <Dumbbell size={28} className="text-white/15" />
                  <p className="text-xs text-white/30">
                    Тренировки ещё не записаны
                  </p>
                  <button
                    onClick={() => navigate("/workout-plan")}
                    className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors"
                  >
                    Открыть план тренировок →
                  </button>
                </div>
              ) : (
                <div className="space-y-2">
                  {data.recent_workouts.map(w => (
                    <div
                      key={w.id}
                      className="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-white/[0.03] border border-white/[0.05]"
                    >
                      <div className="w-7 h-7 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center flex-shrink-0">
                        <Dumbbell size={12} className="text-cyan-400" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-white truncate">
                          {w.exercise}
                        </p>
                        <p className="text-[11px] text-white/30">
                          {w.sets}×{w.reps}
                          {w.weight_kg ? ` @ ${w.weight_kg}кг` : ""}
                        </p>
                      </div>
                      <p className="text-[11px] text-white/25 flex-shrink-0">
                        {new Date(w.logged_at).toLocaleDateString("ru-RU", {
                          day: "numeric",
                          month: "short",
                        })}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Weight history table */}
            {data.weight_history.length > 0 && (
              <div className="rounded-2xl bg-white/[0.03] border border-white/[0.07] p-5">
                <p className="text-sm font-semibold text-white mb-4">
                  История веса
                </p>
                <div className="space-y-1.5 max-h-64 overflow-y-auto">
                  {data.weight_history.map((entry, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-white/[0.03] transition-colors"
                    >
                      <p className="text-xs text-white/40">
                        {new Date(entry.logged_at).toLocaleDateString("ru-RU", {
                          day: "numeric",
                          month: "long",
                          year: "numeric",
                        })}
                      </p>
                      <p className="text-sm font-semibold text-white">
                        {entry.weight} кг
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </main>

      {showLogModal && (
        <LogWeightModal
          current={data?.current_weight ?? null}
          onLog={w => logWeightMutation.mutate({ weight: w })}
          isLoading={logWeightMutation.isPending}
          onClose={() => setShowLogModal(false)}
        />
      )}
    </div>
  );
}
