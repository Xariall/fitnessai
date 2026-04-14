import { useMemo } from "react";

interface Props {
  activeDate: string; // YYYY-MM-DD
  onDateChange: (date: string) => void;
}

const DAY_ABBR = ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"];
const MONTH_ABBR = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

function toLocalISO(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function getWeekDays(): Date[] {
  const today = new Date();
  const dow = today.getDay(); // 0=Sun
  const monday = new Date(today);
  monday.setDate(today.getDate() - ((dow + 6) % 7));
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    return d;
  });
}

export default function DayTabs({ activeDate, onDateChange }: Props) {
  const days = useMemo(getWeekDays, []);
  const todayISO = useMemo(() => toLocalISO(new Date()), []);

  return (
    <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-hide">
      {days.map(day => {
        const iso = toLocalISO(day);
        const isActive = iso === activeDate;
        const isToday = iso === todayISO;

        return (
          <button
            key={iso}
            onClick={() => onDateChange(iso)}
            className={`flex flex-col items-center gap-1 px-3 py-2.5 rounded-xl border transition-all duration-200 min-w-[52px] flex-shrink-0 ${
              isActive
                ? "bg-purple-500/30 border-purple-500/60 text-white"
                : "bg-white/5 border-white/10 text-white/50 hover:border-white/20 hover:text-white/80"
            }`}
          >
            <span className="text-xs font-medium">{DAY_ABBR[day.getDay()]}</span>
            <span className={`text-lg font-bold leading-none ${isActive ? "text-white" : ""}`}>
              {day.getDate()}
            </span>
            <span className="text-[10px] opacity-60">{MONTH_ABBR[day.getMonth()]}</span>
            {isToday && (
              <div className={`w-1 h-1 rounded-full ${isActive ? "bg-white" : "bg-purple-400"}`} />
            )}
          </button>
        );
      })}
    </div>
  );
}
