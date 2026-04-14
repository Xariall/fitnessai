import type { RouterOutputs } from "@/lib/trpc";

type PlanData = RouterOutputs["nutrition"]["getPlan"]["plan"];
type DailyNorm = RouterOutputs["nutrition"]["getPlan"]["daily_norm"];
type DiaryData = RouterOutputs["nutrition"]["getDiary"];

interface Props {
  plan: PlanData;
  dailyNorm: DailyNorm;
  diary?: DiaryData;
}

interface MacroConfig {
  label: string;
  unit: string;
  fact: number;
  norm: number;
  planned: number;
  // SVG ring
  ringColor: string;
  trackColor: string;
  glowColor: string;
  // Card theming (inline styles to guarantee rendering — Tailwind purge can drop dynamic classes)
  cardBg: string;
  cardBorder: string;
  cardShadow: string;
  valueColor: string;
}

function calcTotals(
  plan: PlanData,
  onlyConsumed = false
): { cal: number; p: number; f: number; c: number } {
  if (!plan) return { cal: 0, p: 0, f: 0, c: 0 };
  const items = Object.values(plan.meals)
    .flat()
    .filter(item => !onlyConsumed || item.consumed);
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

const R = 32;
const CIRC = 2 * Math.PI * R; // ≈ 201

function MacroCard({ m }: { m: MacroConfig }) {
  const pct = m.norm > 0 ? Math.min(m.fact / m.norm, 1) : 0;
  const offset = CIRC * (1 - pct);

  return (
    <div
      className="flex flex-col items-center gap-3 p-4 rounded-2xl backdrop-blur-sm"
      style={{
        background: m.cardBg,
        border: `1px solid ${m.cardBorder}`,
        boxShadow: m.cardShadow,
      }}
    >
      {/* Circular ring */}
      <div className="relative w-[76px] h-[76px]">
        <svg
          width="76"
          height="76"
          viewBox="0 0 76 76"
          style={{ transform: "rotate(-90deg)" }}
        >
          {/* Track */}
          <circle
            cx="38"
            cy="38"
            r={R}
            fill="none"
            stroke={m.trackColor}
            strokeWidth="7"
          />
          {/* Progress arc */}
          <circle
            cx="38"
            cy="38"
            r={R}
            fill="none"
            stroke={m.ringColor}
            strokeWidth="7"
            strokeLinecap="round"
            strokeDasharray={CIRC}
            strokeDashoffset={offset}
            style={{
              transition: "stroke-dashoffset 0.9s cubic-bezier(0.16,1,0.3,1)",
              filter: `drop-shadow(0 0 5px ${m.ringColor})`,
            }}
          />
        </svg>
        {/* Center value */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span
            className="text-[17px] font-black leading-none"
            style={{ color: m.valueColor }}
          >
            {m.fact}
          </span>
          <span
            className="text-[9px] mt-0.5"
            style={{ color: `${m.valueColor}80` }}
          >
            {m.unit}
          </span>
        </div>
      </div>

      {/* Label */}
      <div className="text-center w-full">
        <p className="text-[13px] font-bold text-white/90">{m.label}</p>
        <p className="text-[10px] text-white/40 mt-0.5">
          цель&nbsp;
          <span className="text-white/65 font-semibold">{m.norm}</span>
        </p>
      </div>

      {/* Mini progress bar */}
      <div className="w-full">
        <div className="flex justify-between text-[9px] text-white/30 mb-1">
          <span>
            план <span className="text-white/50">{m.planned}</span>
          </span>
          <span style={{ color: m.valueColor }}>{Math.round(pct * 100)}%</span>
        </div>
        <div
          className="h-[3px] w-full rounded-full overflow-hidden"
          style={{ background: m.trackColor }}
        >
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{
              width: `${Math.round(pct * 100)}%`,
              background: m.ringColor,
            }}
          />
        </div>
      </div>
    </div>
  );
}

export default function NutritionSummary({ plan, dailyNorm }: Props) {
  const planned = calcTotals(plan, false);
  const consumed = calcTotals(plan, true);

  const macros: MacroConfig[] = [
    {
      label: "Калории",
      unit: "ккал",
      fact: Math.round(consumed.cal),
      norm: dailyNorm?.target_calories ?? 0,
      planned: Math.round(planned.cal),
      ringColor: "#c084fc",
      trackColor: "rgba(192,132,252,0.18)",
      glowColor: "rgba(192,132,252,0.7)",
      cardBg:
        "linear-gradient(135deg, rgba(126,34,206,0.35) 0%, rgba(88,28,135,0.18) 100%)",
      cardBorder: "rgba(168,85,247,0.45)",
      cardShadow:
        "0 4px 24px rgba(168,85,247,0.22), inset 0 1px 0 rgba(255,255,255,0.06)",
      valueColor: "#d8b4fe",
    },
    {
      label: "Белки",
      unit: "г",
      fact: Math.round(consumed.p),
      norm: dailyNorm?.protein_g ?? 0,
      planned: Math.round(planned.p),
      ringColor: "#60a5fa",
      trackColor: "rgba(96,165,250,0.18)",
      glowColor: "rgba(96,165,250,0.7)",
      cardBg:
        "linear-gradient(135deg, rgba(29,78,216,0.35) 0%, rgba(30,58,138,0.18) 100%)",
      cardBorder: "rgba(59,130,246,0.45)",
      cardShadow:
        "0 4px 24px rgba(59,130,246,0.22), inset 0 1px 0 rgba(255,255,255,0.06)",
      valueColor: "#93c5fd",
    },
    {
      label: "Жиры",
      unit: "г",
      fact: Math.round(consumed.f),
      norm: dailyNorm?.fat_g ?? 0,
      planned: Math.round(planned.f),
      ringColor: "#fb923c",
      trackColor: "rgba(251,146,60,0.18)",
      glowColor: "rgba(251,146,60,0.7)",
      cardBg:
        "linear-gradient(135deg, rgba(194,65,12,0.35) 0%, rgba(154,52,18,0.18) 100%)",
      cardBorder: "rgba(249,115,22,0.45)",
      cardShadow:
        "0 4px 24px rgba(249,115,22,0.22), inset 0 1px 0 rgba(255,255,255,0.06)",
      valueColor: "#fdba74",
    },
    {
      label: "Углеводы",
      unit: "г",
      fact: Math.round(consumed.c),
      norm: dailyNorm?.carbs_g ?? 0,
      planned: Math.round(planned.c),
      ringColor: "#34d399",
      trackColor: "rgba(52,211,153,0.18)",
      glowColor: "rgba(52,211,153,0.7)",
      cardBg:
        "linear-gradient(135deg, rgba(4,120,87,0.35) 0%, rgba(6,78,59,0.18) 100%)",
      cardBorder: "rgba(16,185,129,0.45)",
      cardShadow:
        "0 4px 24px rgba(16,185,129,0.22), inset 0 1px 0 rgba(255,255,255,0.06)",
      valueColor: "#6ee7b7",
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {macros.map(m => (
        <MacroCard key={m.label} m={m} />
      ))}
    </div>
  );
}
