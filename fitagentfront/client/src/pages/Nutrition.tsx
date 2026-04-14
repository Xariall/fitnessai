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
      toast.success("План питания создан!");
      setShowModal(false);
      utils.nutrition.getPlan.invalidate({ date: activeDate });
    },
    onError: (err) => {
      // Try to extract FastAPI detail from the error message JSON
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
    <div className="min-h-screen bg-gradient-dark relative overflow-hidden flex flex-col">
      {/* Background orbs */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-gradient-to-br from-purple-600 to-purple-800 rounded-full blur-3xl opacity-10 animate-float" />
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-gradient-to-br from-cyan-500 to-purple-600 rounded-full blur-3xl opacity-10 animate-float-reverse" />
      </div>

      {/* Header */}
      <header className="relative z-10 w-full border-b border-white/5 backdrop-blur-sm">
        <div className="max-w-3xl mx-auto px-4 md:px-6 py-4 flex items-center gap-4">
          <button
            onClick={() => navigate("/dashboard")}
            className="w-9 h-9 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 flex items-center justify-center text-white/60 hover:text-white transition-all"
          >
            <ChevronLeft size={18} />
          </button>
          <div className="flex-1">
            <h1 className="text-lg font-bold text-white">Питание</h1>
          </div>
          {plan && (
            <button
              onClick={() => setShowModal(true)}
              title="Перегенерировать план"
              className="w-9 h-9 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 flex items-center justify-center text-white/50 hover:text-purple-300 transition-all"
            >
              <RefreshCw size={15} />
            </button>
          )}
        </div>
      </header>

      {/* Main */}
      <main className="relative z-10 flex-1 w-full max-w-3xl mx-auto px-4 md:px-6 py-6 space-y-6">
        {/* Day selector */}
        <DayTabs activeDate={activeDate} onDateChange={setActiveDate} />

        {/* Loading */}
        {planQuery.isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="glass h-28 rounded-2xl border border-white/5 animate-pulse" />
            ))}
          </div>
        ) : plan === null ? (
          /* Empty state */
          <div className="glass p-10 rounded-2xl border border-white/10 flex flex-col items-center gap-5 text-center animate-slide-in-up">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-purple-500/30 to-cyan-500/20 border border-white/10 flex items-center justify-center">
              <Sparkles size={28} className="text-purple-300" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white mb-2">Нет плана на этот день</h2>
              <p className="text-white/40 text-sm max-w-xs">
                Пусть AI составит персональный план питания на основе вашей нормы КБЖУ
              </p>
            </div>
            <button
              onClick={() => setShowModal(true)}
              className="btn-primary flex items-center gap-2"
            >
              <Sparkles size={16} />
              Сгенерировать план
            </button>
          </div>
        ) : (
          <>
            {/* КБЖУ summary */}
            <NutritionSummary
              plan={plan}
              dailyNorm={dailyNorm}
              diary={diaryQuery.data}
            />

            {/* Meal cards */}
            <div className="space-y-4 animate-slide-in-up">
              {mealEntries.map(({ mealType, items }) => (
                <MealCard
                  key={mealType}
                  mealType={mealType}
                  items={items}
                  onUpdateItem={(itemId, weightG) =>
                    updateMutation.mutate({ itemId, weightG })
                  }
                  onDeleteItem={itemId =>
                    deleteMutation.mutate({ itemId })
                  }
                  isUpdating={updateMutation.isPending}
                />
              ))}
            </div>
          </>
        )}
      </main>

      <RegeneratePlanModal
        date={activeDate}
        open={showModal}
        onClose={() => setShowModal(false)}
        onGenerate={notes => generateMutation.mutate({ date: activeDate, notes })}
        isLoading={generateMutation.isPending}
      />
    </div>
  );
}
