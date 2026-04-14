import { useState } from "react";
import { Trash2, Pencil, Check, X } from "lucide-react";
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

interface Props {
  mealType: string;
  items: PlanItem[];
  onUpdateItem: (itemId: number, weightG: number) => void;
  onDeleteItem: (itemId: number) => void;
  isUpdating?: boolean;
}

function ItemRow({
  item,
  onUpdate,
  onDelete,
  isUpdating,
}: {
  item: PlanItem;
  onUpdate: (w: number) => void;
  onDelete: () => void;
  isUpdating: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(String(item.weight_g));

  function commitEdit() {
    const val = parseFloat(draft);
    if (!isNaN(val) && val > 0 && val !== item.weight_g) {
      onUpdate(val);
    }
    setEditing(false);
  }

  function cancelEdit() {
    setDraft(String(item.weight_g));
    setEditing(false);
  }

  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-white/5 last:border-0 group">
      <div className="flex-1 min-w-0">
        <p className="text-sm text-white font-medium truncate">{item.product_name}</p>
        <p className="text-xs text-white/40 mt-0.5">
          {Math.round(item.calories)} ккал · Б {Math.round(item.protein)} · Ж {Math.round(item.fat)} · У{" "}
          {Math.round(item.carbs)}
        </p>
      </div>

      {editing ? (
        <div className="flex items-center gap-1.5">
          <input
            type="number"
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter") commitEdit();
              if (e.key === "Escape") cancelEdit();
            }}
            className="w-16 bg-white/10 border border-purple-500/60 rounded-lg px-2 py-1 text-sm text-white text-center focus:outline-none"
            autoFocus
          />
          <span className="text-xs text-white/40">г</span>
          <button onClick={commitEdit} disabled={isUpdating} className="text-emerald-400 hover:text-emerald-300">
            <Check size={14} />
          </button>
          <button onClick={cancelEdit} className="text-white/30 hover:text-white/60">
            <X size={14} />
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <button
            onClick={() => { setDraft(String(item.weight_g)); setEditing(true); }}
            className="flex items-center gap-1 text-xs text-white/50 hover:text-white/80 transition-colors"
          >
            <span>{item.weight_g}г</span>
            <Pencil size={11} className="opacity-0 group-hover:opacity-100 transition-opacity" />
          </button>
          <button
            onClick={onDelete}
            className="text-white/20 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
          >
            <Trash2 size={14} />
          </button>
        </div>
      )}
    </div>
  );
}

export default function MealCard({ mealType, items, onUpdateItem, onDeleteItem, isUpdating = false }: Props) {
  const label = MEAL_LABELS[mealType] ?? mealType;
  const totalCal = items.reduce((s, i) => s + i.calories, 0);

  return (
    <div className="glass p-5 rounded-2xl border border-white/10">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-white">{label}</h3>
        <span className="text-xs text-white/40">{Math.round(totalCal)} ккал</span>
      </div>

      {items.length === 0 ? (
        <p className="text-sm text-white/30 py-2">Нет блюд</p>
      ) : (
        <div>
          {items.map(item => (
            <ItemRow
              key={item.id}
              item={item}
              onUpdate={w => onUpdateItem(item.id, w)}
              onDelete={() => onDeleteItem(item.id)}
              isUpdating={isUpdating}
            />
          ))}
        </div>
      )}
    </div>
  );
}
