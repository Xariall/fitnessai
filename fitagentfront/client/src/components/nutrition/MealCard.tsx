import { useState } from "react";
import { useLocation } from "wouter";
import { Trash2, Pencil, Check, X, ChevronDown, Plus } from "lucide-react";
import type { RouterOutputs } from "@/lib/trpc";

type GetPlanOutput = RouterOutputs["nutrition"]["getPlan"];
type PlanItem = NonNullable<GetPlanOutput["plan"]>["meals"][string][number];

const MEAL_LABELS: Record<string, string> = {
  breakfast: "Завтрак",
  lunch: "Обед",
  dinner: "Ужин",
  snack: "Перекус",
  other: "Другое",
};

const MEAL_ICONS: Record<string, string> = {
  breakfast: "🌅",
  lunch: "☀️",
  dinner: "🌙",
  snack: "🍎",
  other: "🍽️",
};

interface Props {
  mealType: string;
  items: PlanItem[];
  onUpdateItem: (itemId: number, weightG: number) => void;
  onDeleteItem: (itemId: number) => void;
  onToggleConsumed: (itemId: number, consumed: boolean) => void;
  onAddItem?: () => void;
  isUpdating?: boolean;
  defaultOpen?: boolean;
}

function ItemRow({
  item,
  onUpdate,
  onDelete,
  onToggleConsumed,
  isUpdating,
}: {
  item: PlanItem;
  onUpdate: (w: number) => void;
  onDelete: () => void;
  onToggleConsumed: (consumed: boolean) => void;
  isUpdating: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(String(item.weight_g));
  const [, navigate] = useLocation();

  function commitEdit() {
    const val = parseFloat(draft);
    if (!isNaN(val) && val > 0 && val !== item.weight_g) onUpdate(val);
    setEditing(false);
  }

  function cancelEdit() {
    setDraft(String(item.weight_g));
    setEditing(false);
  }

  return (
    <div
      className={`flex items-center gap-3 py-3 border-b border-white/[0.05] last:border-0 group transition-opacity duration-200 ${item.consumed ? "opacity-60" : "opacity-100"}`}
    >
      {/* Checkbox */}
      <button
        onClick={() => onToggleConsumed(!item.consumed)}
        className={`
          w-5 h-5 rounded-full border-2 flex-shrink-0 flex items-center justify-center
          transition-all duration-200 active:scale-90
          ${
            item.consumed
              ? "bg-emerald-500 border-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]"
              : "border-white/20 hover:border-emerald-400/60 bg-transparent"
          }
        `}
        title={
          item.consumed ? "Отметить как несъеденное" : "Отметить как съеденное"
        }
      >
        {item.consumed && (
          <Check size={11} className="text-white" strokeWidth={3} />
        )}
      </button>

      {/* Name + macros */}
      <div className="flex-1 min-w-0">
        <p
          className={`text-sm font-medium truncate transition-colors ${item.consumed ? "text-white/50 line-through decoration-white/30" : "text-white/90"}`}
        >
          {item.product_name}
        </p>
        <p className="text-[11px] text-white/35 mt-0.5">
          <span className="text-white/50">{Math.round(item.calories)}</span>{" "}
          ккал
          {" · "}Б{" "}
          <span className="text-blue-300/70">{Math.round(item.protein)}</span>
          {" · "}Ж{" "}
          <span className="text-orange-300/70">{Math.round(item.fat)}</span>
          {" · "}У{" "}
          <span className="text-emerald-300/70">{Math.round(item.carbs)}</span>
        </p>
        <button
          type="button"
          onClick={() =>
            navigate(
              `/chat?q=${encodeURIComponent(`Чем можно заменить ${item.product_name} в моём плане питания?`)}`
            )
          }
          className="text-[10px] text-purple-400/50 hover:text-purple-300 transition-colors mt-0.5"
        >
          Чем заменить? →
        </button>
      </div>

      {/* Weight / edit */}
      {editing ? (
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <input
            type="number"
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter") commitEdit();
              if (e.key === "Escape") cancelEdit();
            }}
            className="w-16 bg-white/[0.08] border border-purple-500/60 rounded-lg px-2 py-1 text-sm text-white text-center focus:outline-none focus:border-purple-400"
            autoFocus
          />
          <span className="text-xs text-white/40">г</span>
          <button
            onClick={commitEdit}
            disabled={isUpdating}
            className="text-emerald-400 hover:text-emerald-300 transition-colors"
          >
            <Check size={14} />
          </button>
          <button
            onClick={cancelEdit}
            className="text-white/30 hover:text-white/60 transition-colors"
          >
            <X size={14} />
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Always-visible weight */}
          <span className="text-xs font-semibold text-white/40 group-hover:hidden">
            {item.weight_g}г
          </span>
          {/* Hover controls */}
          <div className="hidden group-hover:flex items-center gap-2">
            <button
              onClick={() => {
                setDraft(String(item.weight_g));
                setEditing(true);
              }}
              className="flex items-center gap-1 text-xs text-white/50 hover:text-white/90 transition-colors"
            >
              <span className="font-medium">{item.weight_g}г</span>
              <Pencil size={10} className="text-white/30" />
            </button>
            <button
              onClick={onDelete}
              className="text-white/20 hover:text-red-400 transition-colors"
            >
              <Trash2 size={13} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function MealCard({
  mealType,
  items,
  onUpdateItem,
  onDeleteItem,
  onToggleConsumed,
  onAddItem,
  isUpdating = false,
  defaultOpen = true,
}: Props) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const label = MEAL_LABELS[mealType] ?? mealType;
  const icon = MEAL_ICONS[mealType] ?? "🍽️";
  const totalCal = items.reduce((s, i) => s + i.calories, 0);
  const consumedCal = items
    .filter(i => i.consumed)
    .reduce((s, i) => s + i.calories, 0);
  const consumedCount = items.filter(i => i.consumed).length;

  return (
    <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-sm overflow-hidden transition-all duration-200 hover:border-white/[0.12]">
      {/* Header */}
      <button
        onClick={() => setIsOpen(v => !v)}
        className="w-full flex items-center gap-3 px-5 py-4 text-left"
      >
        {/* Icon bubble */}
        <div className="w-9 h-9 rounded-xl bg-white/[0.06] flex items-center justify-center text-base flex-shrink-0">
          {icon}
        </div>

        {/* Title + progress */}
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-white/90 text-sm">{label}</p>
          {items.length > 0 && (
            <p className="text-[11px] text-white/35 mt-0.5">
              {consumedCount}/{items.length} съедено
              {consumedCal > 0 && (
                <span className="text-emerald-400/70">
                  {" "}
                  · {Math.round(consumedCal)} ккал
                </span>
              )}
            </p>
          )}
        </div>

        {/* Calorie badge */}
        {items.length > 0 && (
          <span className="text-xs font-semibold text-purple-300/70 bg-purple-500/10 border border-purple-500/20 px-2.5 py-1 rounded-full flex-shrink-0">
            {Math.round(totalCal)} ккал
          </span>
        )}

        <ChevronDown
          size={16}
          className={`text-white/30 flex-shrink-0 transition-transform duration-300 ${isOpen ? "rotate-180" : ""}`}
        />
      </button>

      {/* Body */}
      <div
        className={`overflow-hidden transition-all duration-300 ${isOpen ? "max-h-[700px] opacity-100" : "max-h-0 opacity-0"}`}
      >
        <div className="px-5 pb-4 relative">
          <div className="h-px bg-white/[0.05] mb-1" />

          {items.length === 0 ? (
            <div className="flex items-center justify-between py-4">
              <p className="text-sm text-white/25 italic">Нет блюд</p>
              {onAddItem && (
                <button
                  onClick={onAddItem}
                  className="flex items-center gap-1.5 text-xs text-purple-400 hover:text-purple-300 transition-colors"
                >
                  <Plus size={14} /> Добавить
                </button>
              )}
            </div>
          ) : (
            <>
              <div>
                {items.map(item => (
                  <ItemRow
                    key={item.id}
                    item={item}
                    onUpdate={w => onUpdateItem(item.id, w)}
                    onDelete={() => onDeleteItem(item.id)}
                    onToggleConsumed={consumed =>
                      onToggleConsumed(item.id, consumed)
                    }
                    isUpdating={isUpdating}
                  />
                ))}
              </div>

              {onAddItem && (
                <div className="flex justify-end mt-3">
                  <button
                    onClick={onAddItem}
                    className="w-9 h-9 rounded-full bg-purple-600/80 hover:bg-purple-500 border border-purple-500/50 flex items-center justify-center text-white shadow-[0_4px_14px_rgba(168,85,247,0.35)] hover:shadow-[0_4px_18px_rgba(168,85,247,0.5)] transition-all duration-200 active:scale-95"
                    title="Добавить блюдо"
                  >
                    <Plus size={18} />
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
