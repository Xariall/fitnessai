import type { RouterOutputs } from "@/lib/trpc";

type PlanData = RouterOutputs["nutrition"]["getPlan"]["plan"];
type DailyNorm = RouterOutputs["nutrition"]["getPlan"]["daily_norm"];
type DiaryData = RouterOutputs["nutrition"]["getDiary"];

interface Props {
  plan: PlanData;
  dailyNorm: DailyNorm;
  diary: DiaryData | undefined;
}

interface MacroCard {
  label: string;
  unit: string;
  fact: number;
  norm: number;
  planned: number;
  color: string;
  bg: string;
}

function calcPlanTotals(plan: PlanData): { cal: number; p: number; f: number; c: number } {
  if (!plan) return { cal: 0, p: 0, f: 0, c: 0 };
  const items = Object.values(plan.meals).flat();
  return items.reduce(
    (acc, item) => ({
      cal: acc.cal + item.calories,
      p: acc.p + item.protein,
      f: acc.f + item.fat,
      c: acc.c + item.carbs,
    }),
    { cal: 0, p: 0, f: 0, c: 0 }
  );
}

function ProgressBar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
      <div
        className={`h-full rounded-full transition-all duration-500 ${color}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export default function NutritionSummary({ plan, dailyNorm, diary }: Props) {
  const planTotals = calcPlanTotals(plan);
  const fact = diary?.summary;

  const cards: MacroCard[] = [
    {
      label: "Калории",
      unit: "ккал",
      fact: Math.round(fact?.calories ?? 0),
      norm: dailyNorm?.target_calories ?? 0,
      planned: Math.round(planTotals.cal),
      color: "bg-purple-500",
      bg: "from-purple-500/15 to-purple-600/5",
    },
    {
      label: "Белки",
      unit: "г",
      fact: Math.round(fact?.protein ?? 0),
      norm: dailyNorm?.protein_g ?? 0,
      planned: Math.round(planTotals.p),
      color: "bg-cyan-500",
      bg: "from-cyan-500/15 to-cyan-600/5",
    },
    {
      label: "Жиры",
      unit: "г",
      fact: Math.round(fact?.fat ?? 0),
      norm: dailyNorm?.fat_g ?? 0,
      planned: Math.round(planTotals.f),
      color: "bg-orange-400",
      bg: "from-orange-400/15 to-orange-500/5",
    },
    {
      label: "Углеводы",
      unit: "г",
      fact: Math.round(fact?.carbs ?? 0),
      norm: dailyNorm?.carbs_g ?? 0,
      planned: Math.round(planTotals.c),
      color: "bg-emerald-400",
      bg: "from-emerald-400/15 to-emerald-500/5",
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {cards.map(card => (
        <div
          key={card.label}
          className={`glass-sm bg-gradient-to-br ${card.bg} p-4 rounded-2xl border border-white/10 flex flex-col gap-3`}
        >
          <span className="text-xs text-white/50 font-medium">{card.label}</span>

          <div className="flex items-end gap-1">
            <span className="text-2xl font-bold text-white leading-none">{card.fact}</span>
            <span className="text-xs text-white/40 mb-0.5">{card.unit}</span>
          </div>

          <ProgressBar value={card.fact} max={card.norm} color={card.color} />

          <div className="flex justify-between text-[11px]">
            <span className="text-white/30">
              план <span className="text-white/60">{card.planned}</span>
            </span>
            <span className="text-white/30">
              норма <span className="text-white/60">{card.norm}</span>
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
