import { useAuth } from "@/_core/hooks/useAuth";
import { trpc } from "@/lib/trpc";
import { useState, useEffect } from "react";
import { useLocation } from "wouter";
import { ChevronRight, ChevronLeft, User, Activity, Heart, Target } from "lucide-react";
import { toast } from "sonner";

type Step = 0 | 1 | 2 | 3;

const STEPS = [
  { icon: User,     label: "Профиль" },
  { icon: Activity, label: "Параметры" },
  { icon: Target,   label: "Цель" },
  { icon: Heart,    label: "Здоровье" },
];

const GENDERS = [
  { value: "male",   label: "Мужской" },
  { value: "female", label: "Женский" },
  { value: "other",  label: "Другой" },
];

const ACTIVITIES = [
  { value: "sedentary", label: "Сидячий образ жизни", desc: "Офис, мало движения" },
  { value: "moderate",  label: "Умеренная активность", desc: "1–3 тренировки в неделю" },
  { value: "active",    label: "Активный",              desc: "4–5 тренировок в неделю" },
  { value: "athlete",   label: "Атлет",                 desc: "Ежедневные интенсивные тренировки" },
];

const GOALS = [
  { value: "lose",          label: "Похудеть",        desc: "Снизить процент жира" },
  { value: "gain",          label: "Набрать массу",   desc: "Увеличить мышечную массу" },
  { value: "maintain",      label: "Поддерживать",    desc: "Сохранить текущую форму" },
  { value: "recomposition", label: "Рекомпозиция",    desc: "Жир ↓ мышцы ↑ одновременно" },
];

export default function Onboarding() {
  const { user, loading } = useAuth();
  const [, navigate] = useLocation();
  const [step, setStep] = useState<Step>(0);

  const [name,     setName]     = useState("");
  const [gender,   setGender]   = useState("");
  const [age,      setAge]      = useState("");
  const [height,   setHeight]   = useState("");
  const [weight,   setWeight]   = useState("");
  const [activity, setActivity] = useState("");
  const [goal,     setGoal]     = useState("");
  const [injuries, setInjuries] = useState("");

  const updateProfile = trpc.profile.update.useMutation({
    onSuccess: () => navigate("/chat"),
    onError: () => toast.error("Ошибка сохранения. Попробуйте ещё раз."),
  });

  useEffect(() => {
    if (!loading && !user) navigate("/");
  }, [loading, user, navigate]);

  useEffect(() => {
    if (user?.name) setName(user.name);
  }, [user]);

  if (loading || !user) return null;

  const canNext: Record<Step, boolean> = {
    0: name.trim().length > 0,
    1: !!gender && !!age && !!height && !!weight,
    2: !!activity && !!goal,
    3: true,
  };

  const handleNext = () => {
    if (step < 3) setStep((s) => (s + 1) as Step);
  };

  const handleBack = () => {
    if (step > 0) setStep((s) => (s - 1) as Step);
  };

  const handleSubmit = () => {
    updateProfile.mutate({
      name:                 name.trim() || undefined,
      age:                  age     ? parseInt(age)     : undefined,
      height:               height  ? parseFloat(height): undefined,
      weight:               weight  ? parseFloat(weight): undefined,
      gender:               (gender  as "male" | "female" | "other") || undefined,
      activity:             (activity as "sedentary" | "moderate" | "active" | "athlete") || undefined,
      goal:                 (goal    as "lose" | "gain" | "maintain" | "recomposition") || undefined,
      injuries:             injuries.trim() || undefined,
      onboarding_completed: true,
    });
  };

  return (
    <div className="min-h-screen bg-gradient-dark relative overflow-hidden flex flex-col items-center justify-center px-4">
      {/* Background orbs */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-gradient-to-br from-purple-600 to-purple-800 rounded-full blur-3xl opacity-10 animate-float" />
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-gradient-to-br from-cyan-500 to-purple-600 rounded-full blur-3xl opacity-10 animate-float-reverse" />
      </div>

      <div className="relative z-10 w-full max-w-lg">
        {/* Logo */}
        <div className="flex items-center gap-3 mb-10 justify-center">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-purple-500/50">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 20v-8M6 20v-4M18 20v-12" />
            </svg>
          </div>
          <span className="text-xl font-bold text-white">FitAgent</span>
        </div>

        {/* Step indicators */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {STEPS.map((s, i) => {
            const Icon = s.icon;
            const active  = i === step;
            const done    = i < step;
            return (
              <div key={i} className="flex items-center gap-2">
                <div className={`w-9 h-9 rounded-full flex items-center justify-center transition-all duration-300 ${
                  active ? "bg-purple-500 shadow-lg shadow-purple-500/40"
                  : done  ? "bg-purple-500/40 border border-purple-500/60"
                  :         "bg-white/5 border border-white/10"
                }`}>
                  <Icon size={16} className={active || done ? "text-white" : "text-white/30"} />
                </div>
                {i < STEPS.length - 1 && (
                  <div className={`w-8 h-px transition-all duration-300 ${done ? "bg-purple-500/60" : "bg-white/10"}`} />
                )}
              </div>
            );
          })}
        </div>

        {/* Card */}
        <div className="glass p-8 rounded-2xl border border-white/10">

          {/* Step 0 — Имя */}
          {step === 0 && (
            <div className="space-y-6 animate-slide-in-down">
              <div>
                <h2 className="text-2xl font-bold text-white mb-1">Привет! Как тебя зовут?</h2>
                <p className="text-white/50 text-sm">Это имя будет использоваться в общении с AI-тренером</p>
              </div>
              <div>
                <label className="block text-sm text-white/60 mb-2">Имя</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Например: Александр"
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white placeholder:text-white/30 focus:outline-none focus:border-purple-500/60 transition-colors"
                />
              </div>
            </div>
          )}

          {/* Step 1 — Параметры тела */}
          {step === 1 && (
            <div className="space-y-6 animate-slide-in-down">
              <div>
                <h2 className="text-2xl font-bold text-white mb-1">Параметры тела</h2>
                <p className="text-white/50 text-sm">Нужны для расчёта КБЖУ и программы тренировок</p>
              </div>

              <div>
                <label className="block text-sm text-white/60 mb-2">Пол</label>
                <div className="grid grid-cols-3 gap-2">
                  {GENDERS.map((g) => (
                    <button
                      key={g.value}
                      onClick={() => setGender(g.value)}
                      className={`py-2.5 rounded-xl text-sm font-medium border transition-all duration-200 ${
                        gender === g.value
                          ? "bg-purple-500/30 border-purple-500/60 text-white"
                          : "bg-white/5 border-white/10 text-white/60 hover:border-white/20"
                      }`}
                    >
                      {g.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm text-white/60 mb-2">Возраст</label>
                  <input
                    type="number"
                    value={age}
                    onChange={(e) => setAge(e.target.value)}
                    placeholder="25"
                    min="10" max="120"
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-3 text-white placeholder:text-white/30 focus:outline-none focus:border-purple-500/60 transition-colors"
                  />
                </div>
                <div>
                  <label className="block text-sm text-white/60 mb-2">Рост (см)</label>
                  <input
                    type="number"
                    value={height}
                    onChange={(e) => setHeight(e.target.value)}
                    placeholder="175"
                    min="100" max="250"
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-3 text-white placeholder:text-white/30 focus:outline-none focus:border-purple-500/60 transition-colors"
                  />
                </div>
                <div>
                  <label className="block text-sm text-white/60 mb-2">Вес (кг)</label>
                  <input
                    type="number"
                    value={weight}
                    onChange={(e) => setWeight(e.target.value)}
                    placeholder="70"
                    min="30" max="300"
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-3 text-white placeholder:text-white/30 focus:outline-none focus:border-purple-500/60 transition-colors"
                  />
                </div>
              </div>
            </div>
          )}

          {/* Step 2 — Активность и цель */}
          {step === 2 && (
            <div className="space-y-6 animate-slide-in-down">
              <div>
                <h2 className="text-2xl font-bold text-white mb-1">Активность и цель</h2>
                <p className="text-white/50 text-sm">Выбери то, что лучше всего тебя описывает</p>
              </div>

              <div>
                <label className="block text-sm text-white/60 mb-2">Уровень активности</label>
                <div className="space-y-2">
                  {ACTIVITIES.map((a) => (
                    <button
                      key={a.value}
                      onClick={() => setActivity(a.value)}
                      className={`w-full flex items-start gap-3 p-3 rounded-xl border text-left transition-all duration-200 ${
                        activity === a.value
                          ? "bg-purple-500/20 border-purple-500/60"
                          : "bg-white/5 border-white/10 hover:border-white/20"
                      }`}
                    >
                      <div className={`w-4 h-4 mt-0.5 rounded-full border-2 flex-shrink-0 transition-colors ${
                        activity === a.value ? "border-purple-400 bg-purple-400" : "border-white/30"
                      }`} />
                      <div>
                        <p className="text-sm font-medium text-white">{a.label}</p>
                        <p className="text-xs text-white/40">{a.desc}</p>
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-sm text-white/60 mb-2">Цель</label>
                <div className="grid grid-cols-2 gap-2">
                  {GOALS.map((g) => (
                    <button
                      key={g.value}
                      onClick={() => setGoal(g.value)}
                      className={`p-3 rounded-xl border text-left transition-all duration-200 ${
                        goal === g.value
                          ? "bg-purple-500/20 border-purple-500/60"
                          : "bg-white/5 border-white/10 hover:border-white/20"
                      }`}
                    >
                      <p className="text-sm font-medium text-white">{g.label}</p>
                      <p className="text-xs text-white/40 mt-0.5">{g.desc}</p>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Step 3 — Здоровье */}
          {step === 3 && (
            <div className="space-y-6 animate-slide-in-down">
              <div>
                <h2 className="text-2xl font-bold text-white mb-1">Здоровье и травмы</h2>
                <p className="text-white/50 text-sm">Это поможет AI-тренеру составить безопасную программу</p>
              </div>

              <div>
                <label className="block text-sm text-white/60 mb-2">
                  Травмы, заболевания или ограничения{" "}
                  <span className="text-white/30">(необязательно)</span>
                </label>
                <textarea
                  value={injuries}
                  onChange={(e) => setInjuries(e.target.value)}
                  placeholder="Например: боль в пояснице, проблемы с коленом, гипертония..."
                  rows={4}
                  maxLength={2000}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white placeholder:text-white/30 focus:outline-none focus:border-purple-500/60 transition-colors resize-none"
                />
                <p className="text-xs text-white/20 mt-1 text-right">{injuries.length}/2000</p>
              </div>

              <div className="p-4 rounded-xl bg-purple-500/10 border border-purple-500/20">
                <p className="text-xs text-purple-300">
                  Данные хранятся только для персонализации тренировок и не передаются третьим лицам.
                </p>
              </div>
            </div>
          )}

          {/* Navigation */}
          <div className="flex items-center justify-between mt-8">
            <button
              onClick={handleBack}
              className={`flex items-center gap-1 text-sm text-white/50 hover:text-white transition-colors ${step === 0 ? "invisible" : ""}`}
            >
              <ChevronLeft size={16} /> Назад
            </button>

            {step < 3 ? (
              <button
                onClick={handleNext}
                disabled={!canNext[step]}
                className="btn-primary flex items-center gap-1 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Далее <ChevronRight size={16} />
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                disabled={updateProfile.isPending}
                className="btn-primary flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {updateProfile.isPending ? "Сохранение..." : "Начать тренировки"}
                {!updateProfile.isPending && <ChevronRight size={16} />}
              </button>
            )}
          </div>
        </div>

        <p className="text-center text-white/20 text-xs mt-6">
          Шаг {step + 1} из {STEPS.length}
        </p>
      </div>
    </div>
  );
}
