import { useMemo } from "react";

interface Props {
  activeDate: string; // YYYY-MM-DD
  onDateChange: (date: string) => void;
  completedDates?: string[];
}

const DAY_ABBR = ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"];

function toLocalISO(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function getWeekDays(): Date[] {
  const today = new Date();
  const dow = today.getDay();
  const monday = new Date(today);
  monday.setDate(today.getDate() - ((dow + 6) % 7));
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    return d;
  });
}

export default function DayTabs({
  activeDate,
  onDateChange,
  completedDates = [],
}: Props) {
  const days = useMemo(getWeekDays, []);
  const todayISO = useMemo(() => toLocalISO(new Date()), []);

  return (
    <div className="rounded-2xl border border-white/[0.09] bg-white/[0.03] p-1.5 flex gap-1">
      {days.map(day => {
        const iso = toLocalISO(day);
        const isActive = iso === activeDate;
        const isToday = iso === todayISO;
        const isCompleted = completedDates.includes(iso);
        const isPast = iso < todayISO && !isToday;

        return (
          <button
            key={iso}
            onClick={() => onDateChange(iso)}
            className={`
              flex-1 flex flex-col items-center py-3 rounded-xl border transition-all duration-200
              ${
                isActive
                  ? "bg-purple-600 border-purple-400/60 shadow-[0_0_20px_rgba(168,85,247,0.45)] scale-[1.02]"
                  : "border-transparent hover:bg-white/[0.06]"
              }
            `}
          >
            {/* Day abbr */}
            <span
              className={`text-[10px] font-bold uppercase tracking-widest mb-1.5 ${
                isActive ? "text-purple-200" : "text-white/40"
              }`}
            >
              {DAY_ABBR[day.getDay()]}
            </span>

            {/* Day number */}
            <span
              className={`text-[22px] font-black leading-none ${
                isActive
                  ? "text-white"
                  : isToday
                    ? "text-white/90"
                    : isPast
                      ? "text-white/45"
                      : "text-white/30"
              }`}
            >
              {day.getDate()}
            </span>

            {/* Status indicator */}
            <div className="mt-2 h-1.5 flex items-center justify-center">
              {isCompleted ? (
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_5px_rgba(52,211,153,0.9)]" />
              ) : isToday && !isActive ? (
                <div className="w-1.5 h-1.5 rounded-full bg-purple-400/80" />
              ) : isActive ? (
                <div className="w-4 h-0.5 rounded-full bg-white/50" />
              ) : null}
            </div>
          </button>
        );
      })}
    </div>
  );
}
