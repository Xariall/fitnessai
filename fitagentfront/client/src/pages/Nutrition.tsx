import { useState, useEffect } from "react";
import { useLocation } from "wouter";
import { ChevronLeft, Sparkles, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/_core/hooks/useAuth";
import { trpc } from "@/lib/trpc";
import DayTabs from "@/components/nutrition/DayTabs";
import NutritionSummary from "@/components/nutrition/NutritionSummary";
import MealCard from "@/components/nutrition/MealCard";
import RegeneratePlanModal from "@/components/nutrition/RegeneratePlanModal";
import NutritionAssistant, { NutritionAssistantFAB } from "@/components/nutrition/NutritionAssistant";

function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const MEAL_ORDER = ["breakfast", "lunch", "dinner", "snack"];

export default function Nutrition() {
  const { isAuthenticated, loading } = useAuth();
  const [, navigate] = useLocation();

  const [activeDate, setActiveDate] = useState(todayISO);
  const [showModal, setShowModal] = useState(false);
  const [showAssistant, setShowAssistant] = useState(false);

  useEffect(() => {
    if (!loading && !isAuthenticated) navigate("/");
  }, [loading, isAuthenticated, navigate]);

  const utils = trpc.useUtils();

  const planQuery = trpc.nutrition.getPlan.useQuery(
    { date: activeDate },
    { enabled: isAuthenticated, retry: false }
  );

  const diaryQuery = trpc.nutrition.getDiary.useQuery(
    { date: activeDate },
    { enabled: isAuthenticated, retry: false }
  );

  const generateMutation = trpc.nutrition.generatePlan.useMutation({
    onSuccess: () => {
      toast.success("7-дневный план питания создан!");
      setShowModal(false);
      utils.nutrition.getPlan.invalidate();
    },
    onError: err => {
      const match = err.message.match(/"detail"\s*:\s*"([^"]+)"/);
      if (match) {
        toast.error(match[1]);
      } else if (err.message.includes("500")) {
        toast.error("Агент не смог составить план. Попробуйте ещё раз.");
      } else {
        toast.error(err.message);
      }
    },
  });

  const updateMutation = trpc.nutrition.updateItem.useMutation({
    onSuccess: () => utils.nutrition.getPlan.invalidate({ date: activeDate }),
    onError: () => toast.error("Не удалось обновить порцию."),
  });

  const deleteMutation = trpc.nutrition.deleteItem.useMutation({
    onSuccess: () => utils.nutrition.getPlan.invalidate({ date: activeDate }),
    onError: () => toast.error("Не удалось удалить блюдо."),
  });

  const toggleConsumedMutation = trpc.nutrition.toggleConsumed.useMutation({
    onSuccess: () => utils.nutrition.getPlan.invalidate({ date: activeDate }),
    onError: () => toast.error("Не удалось обновить статус."),
  });

  const plan = planQuery.data?.plan ?? null;
  const dailyNorm = planQuery.data?.daily_norm ?? null;

  const mealEntries = plan
    ? [
        ...MEAL_ORDER.filter(k => k in plan.meals),
        ...Object.keys(plan.meals).filter(k => !MEAL_ORDER.includes(k)),
      ].map(mealType => ({ mealType, items: plan.meals[mealType] ?? [] }))
    : [];

  if (loading || !isAuthenticated) return null;

  return (
    <div className="min-h-screen bg-[#0f0a1e] relative overflow-hidden flex flex-col">
      {/* Ambient background orbs */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none select-none">
        <div className="absolute -top-56 -right-56 w-[500px] h-[500px] bg-purple-700 rounded-full blur-[120px] opacity-[0.07]" />
        <div className="absolute top-1/2 -left-40 w-[400px] h-[400px] bg-indigo-600 rounded-full blur-[100px] opacity-[0.06]" />
        <div className="absolute -bottom-60 right-1/3 w-[460px] h-[460px] bg-violet-800 rounded-full blur-[110px] opacity-[0.05]" />
      </div>

      {/* Header */}
      <header className="relative z-10 w-full border-b border-white/[0.05] bg-[#0f0a1e]/80 backdrop-blur-md sticky top-0">
        <div className="max-w-3xl mx-auto px-4 md:px-6 py-4 flex items-center gap-3">
          <button
            onClick={() => navigate("/dashboard")}
            className="w-9 h-9 rounded-xl bg-white/[0.05] border border-white/[0.08] hover:bg-white/[0.09] flex items-center justify-center text-white/50 hover:text-white transition-all duration-200"
          >
            <ChevronLeft size={18} />
          </button>

          <div className="flex-1">
            <h1 className="text-base font-bold text-white tracking-tight">
              Питание
            </h1>
            {plan && (
              <p className="text-[11px] text-white/30 mt-0.5">
                {mealEntries.length} приёмов пищи
              </p>
            )}
          </div>

          {plan && (
            <button
              onClick={() => setShowModal(true)}
              title="Перегенерировать план"
              className="w-9 h-9 rounded-xl bg-white/[0.05] border border-white/[0.08] hover:bg-purple-500/10 hover:border-purple-500/30 flex items-center justify-center text-white/40 hover:text-purple-300 transition-all duration-200"
            >
              <RefreshCw size={15} />
            </button>
          )}
        </div>
      </header>

      {/* Main content */}
      <main className="relative z-10 flex-1 w-full max-w-3xl mx-auto px-4 md:px-6 py-6 space-y-6">
        {/* Weekly calendar strip */}
        <DayTabs activeDate={activeDate} onDateChange={setActiveDate} />

        {/* Loading skeleton */}
        {planQuery.isLoading ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[1, 2, 3, 4].map(i => (
                <div
                  key={i}
                  className="h-44 rounded-2xl bg-white/[0.04] border border-white/[0.06] animate-pulse"
                />
              ))}
            </div>
            {[1, 2, 3].map(i => (
              <div
                key={i}
                className="h-20 rounded-2xl bg-white/[0.03] border border-white/[0.06] animate-pulse"
              />
            ))}
          </div>
        ) : plan === null ? (
          /* Empty state */
          <div className="flex flex-col items-center gap-6 py-16 text-center">
            <div className="relative">
              <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-purple-500/20 to-violet-600/10 border border-purple-500/20 flex items-center justify-center">
                <Sparkles size={32} className="text-purple-300" />
              </div>
              <div className="absolute inset-0 rounded-2xl blur-xl bg-purple-500/10" />
            </div>

            <div>
              <h2 className="text-xl font-bold text-white mb-2">
                Нет плана на этот день
              </h2>
              <p className="text-sm text-white/35 max-w-xs leading-relaxed">
                Пусть AI составит персональный план питания на основе вашей
                нормы КБЖУ
              </p>
            </div>

            <button
              onClick={() => setShowModal(true)}
              className="flex items-center gap-2.5 px-6 py-3 rounded-2xl bg-purple-600 hover:bg-purple-500 border border-purple-500/50 text-white font-semibold text-sm shadow-[0_4px_20px_rgba(168,85,247,0.4)] hover:shadow-[0_4px_28px_rgba(168,85,247,0.55)] transition-all duration-200 active:scale-[0.97]"
            >
              <Sparkles size={16} />
              Сгенерировать план
            </button>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Macro rings */}
            <NutritionSummary plan={plan} dailyNorm={dailyNorm} />

            {/* Section label */}
            <div className="flex items-center gap-3">
              <span className="text-xs font-semibold text-white/30 uppercase tracking-widest">
                Приёмы пищи
              </span>
              <div className="flex-1 h-px bg-white/[0.05]" />
            </div>

            {/* Meal cards */}
            <div className="space-y-3">
              {mealEntries.map(({ mealType, items }) => (
                <MealCard
                  key={mealType}
                  mealType={mealType}
                  items={items}
                  onUpdateItem={(itemId, weightG) =>
                    updateMutation.mutate({ itemId, weightG })
                  }
                  onDeleteItem={itemId => deleteMutation.mutate({ itemId })}
                  onToggleConsumed={(itemId, consumed) =>
                    toggleConsumedMutation.mutate({ itemId, consumed })
                  }
                  isUpdating={updateMutation.isPending}
                  defaultOpen={["breakfast", "lunch", "dinner"].includes(
                    mealType
                  )}
                />
              ))}
            </div>
          </div>
        )}
      </main>

      <RegeneratePlanModal
        date={activeDate}
        open={showModal}
        onClose={() => setShowModal(false)}
        onGenerate={(notes, mealTypes) =>
          generateMutation.mutate({
            date: activeDate,
            notes,
            meal_types: mealTypes,
          })
        }
        isLoading={generateMutation.isPending}
      />

      {/* RAG Nutrition Assistant */}
      <NutritionAssistant
        open={showAssistant}
        onClose={() => setShowAssistant(false)}
      />
      {!showAssistant && (
        <NutritionAssistantFAB onClick={() => setShowAssistant(true)} />
      )}
    </div>
  );
}
