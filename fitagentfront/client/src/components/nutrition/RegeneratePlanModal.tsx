import { useState } from "react";
import { X, Sparkles } from "lucide-react";

type MealType = "breakfast" | "lunch" | "dinner" | "snack";

const MEAL_OPTIONS: { id: MealType; label: string; emoji: string }[] = [
  { id: "breakfast", label: "Завтрак", emoji: "🌅" },
  { id: "lunch", label: "Обед", emoji: "☀️" },
  { id: "dinner", label: "Ужин", emoji: "🌙" },
  { id: "snack", label: "Перекус", emoji: "🍎" },
];

const PRESETS: { label: string; meals: MealType[] }[] = [
  { label: "1×", meals: ["dinner"] },
  { label: "2×", meals: ["lunch", "dinner"] },
  { label: "3×", meals: ["breakfast", "lunch", "dinner"] },
  { label: "3× + перекус", meals: ["breakfast", "lunch", "dinner", "snack"] },
];

interface Props {
  date: string;
  open: boolean;
  onClose: () => void;
  onGenerate: (notes: string, mealTypes: MealType[]) => void;
  isLoading: boolean;
}

export default function RegeneratePlanModal({
  date,
  open,
  onClose,
  onGenerate,
  isLoading,
}: Props) {
  const [notes, setNotes] = useState("");
  const [selectedMeals, setSelectedMeals] = useState<Set<MealType>>(
    new Set(["breakfast", "lunch", "dinner", "snack"])
  );

  if (!open) return null;

  function toggleMeal(id: MealType) {
    setSelectedMeals(prev => {
      // Must keep at least one meal
      if (prev.has(id) && prev.size === 1) return prev;
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function applyPreset(meals: MealType[]) {
    setSelectedMeals(new Set(meals));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const order: MealType[] = ["breakfast", "lunch", "dinner", "snack"];
    const ordered = order.filter(m => selectedMeals.has(m));
    onGenerate(notes, ordered);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-md glass p-6 rounded-2xl border border-white/10 animate-slide-in-up">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-lg font-bold text-white">Сгенерировать план</h2>
            <p className="text-xs text-white/40 mt-0.5">{date}</p>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center text-white/50 hover:text-white hover:bg-white/10 transition-all"
          >
            <X size={14} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Meal type selection */}
          <div>
            <label className="block text-sm text-white/60 mb-2">
              Приёмы пищи
            </label>

            {/* Presets */}
            <div className="flex gap-1.5 mb-3 flex-wrap">
              {PRESETS.map(preset => {
                const active =
                  preset.meals.length === selectedMeals.size &&
                  preset.meals.every(m => selectedMeals.has(m));
                return (
                  <button
                    key={preset.label}
                    type="button"
                    onClick={() => applyPreset(preset.meals)}
                    className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-all"
                    style={
                      active
                        ? {
                            background: "rgba(168,85,247,0.25)",
                            border: "1px solid rgba(168,85,247,0.5)",
                            color: "#d8b4fe",
                          }
                        : {
                            background: "rgba(255,255,255,0.05)",
                            border: "1px solid rgba(255,255,255,0.08)",
                            color: "rgba(255,255,255,0.45)",
                          }
                    }
                  >
                    {preset.label}
                  </button>
                );
              })}
            </div>

            {/* Individual toggles */}
            <div className="grid grid-cols-4 gap-2">
              {MEAL_OPTIONS.map(opt => {
                const active = selectedMeals.has(opt.id);
                const disabled = active && selectedMeals.size === 1;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    disabled={disabled}
                    onClick={() => toggleMeal(opt.id)}
                    className="flex flex-col items-center gap-1.5 py-3 rounded-xl text-xs font-medium transition-all disabled:opacity-40"
                    style={
                      active
                        ? {
                            background: "rgba(168,85,247,0.2)",
                            border: "1px solid rgba(168,85,247,0.4)",
                            color: "#d8b4fe",
                          }
                        : {
                            background: "rgba(255,255,255,0.03)",
                            border: "1px solid rgba(255,255,255,0.07)",
                            color: "rgba(255,255,255,0.3)",
                          }
                    }
                  >
                    <span className="text-base leading-none">{opt.emoji}</span>
                    <span>{opt.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Notes */}
          <div>
            <label className="block text-sm text-white/60 mb-2">
              Пожелания <span className="text-white/30">(необязательно)</span>
            </label>
            <textarea
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="Например: без глютена, больше белка, бюджетные продукты..."
              rows={3}
              maxLength={1000}
              disabled={isLoading}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white placeholder:text-white/30 focus:outline-none focus:border-purple-500/60 transition-colors resize-none text-sm"
            />
            <p className="text-right text-[11px] text-white/20 mt-1">
              {notes.length}/1000
            </p>
          </div>

          <div className="p-3 rounded-xl bg-purple-500/10 border border-purple-500/20 text-xs text-purple-300">
            AI составит план на 7 дней с учётом вашей нормы КБЖУ и пожеланий.
            Переключайтесь между днями в календаре — каждый день уже будет
            заполнен.
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Генерирую план...
              </>
            ) : (
              <>
                <Sparkles size={16} />
                Сгенерировать план
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
