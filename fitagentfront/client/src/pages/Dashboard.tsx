import { useAuth } from "@/_core/hooks/useAuth";
import { useLocation } from "wouter";
import { useEffect } from "react";
import {
  MessageCircle,
  Dumbbell,
  Apple,
  TrendingUp,
  LogOut,
  ChevronRight,
  Instagram,
  Twitter,
  Github,
} from "lucide-react";

const CARDS = [
  {
    icon: MessageCircle,
    title: "Чат с тренером",
    desc: "Задавай вопросы и получай персональные советы от AI-тренера в реальном времени",
    href: "/chat",
    accent: "from-purple-500/20 to-purple-600/10",
    border: "border-purple-500/30 hover:border-purple-500/60",
    iconBg: "from-purple-500/30 to-purple-600/20",
    iconColor: "text-purple-300",
    shadow: "hover:shadow-purple-500/20",
  },
  {
    icon: Dumbbell,
    title: "План тренировок",
    desc: "Индивидуальная программа упражнений с учётом твоей цели и уровня подготовки",
    href: "/workout-plan",
    accent: "from-cyan-500/20 to-cyan-600/10",
    border: "border-cyan-500/30 hover:border-cyan-500/60",
    iconBg: "from-cyan-500/30 to-cyan-600/20",
    iconColor: "text-cyan-300",
    shadow: "hover:shadow-cyan-500/20",
  },
  {
    icon: Apple,
    title: "План питания",
    desc: "Трекинг КБЖУ, дневник питания и рекомендации по рациону под твои параметры",
    href: "/nutrition",
    accent: "from-emerald-500/20 to-emerald-600/10",
    border: "border-emerald-500/30 hover:border-emerald-500/60",
    iconBg: "from-emerald-500/30 to-emerald-600/20",
    iconColor: "text-emerald-300",
    shadow: "hover:shadow-emerald-500/20",
  },
  {
    icon: TrendingUp,
    title: "Мой прогресс",
    desc: "Замеры, вес и динамика — следи за результатами и адаптируй план",
    href: "/progress",
    accent: "from-orange-500/20 to-orange-600/10",
    border: "border-orange-500/30 hover:border-orange-500/60",
    iconBg: "from-orange-500/30 to-orange-600/20",
    iconColor: "text-orange-300",
    shadow: "hover:shadow-orange-500/20",
  },
];

export default function Dashboard() {
  const { user, isAuthenticated, loading, logout } = useAuth();
  const [, navigate] = useLocation();

  useEffect(() => {
    if (!loading && !isAuthenticated) navigate("/");
  }, [loading, isAuthenticated, navigate]);

  if (loading || !isAuthenticated) return null;

  return (
    <div className="min-h-screen bg-gradient-dark relative overflow-hidden flex flex-col">
      {/* Background orbs */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-96 h-96 bg-gradient-to-br from-purple-600 to-purple-800 rounded-full blur-3xl opacity-10 animate-float" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 bg-gradient-to-br from-cyan-500 to-purple-600 rounded-full blur-3xl opacity-10 animate-float-reverse" />
      </div>

      {/* Header */}
      <header className="relative z-10 w-full border-b border-white/5 backdrop-blur-sm">
        <div className="max-w-6xl mx-auto px-4 md:px-6 py-4 flex items-center justify-between">
          {/* Logo */}
          <button
            onClick={() => navigate("/")}
            className="flex items-center gap-3 group"
          >
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-purple-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-purple-500/40 group-hover:shadow-purple-500/60 transition-all duration-300">
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="white"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12 20v-8M6 20v-4M18 20v-12" />
              </svg>
            </div>
            <span className="text-lg font-bold text-white">FitAgent</span>
          </button>

          {/* Nav */}
          <nav className="hidden md:flex items-center gap-6">
            <button
              onClick={() => navigate("/chat")}
              className="text-sm text-white/60 hover:text-white transition-colors"
            >
              Чат
            </button>
            <button
              onClick={() => navigate("/dashboard")}
              className="text-sm text-white font-medium"
            >
              Главная
            </button>
          </nav>

          {/* User */}
          <div className="flex items-center gap-3">
            <div className="hidden sm:flex flex-col items-end">
              <span className="text-sm text-white font-medium leading-none">
                {user?.name || "Пользователь"}
              </span>
              <span className="text-xs text-white/40 mt-0.5">
                {user?.email}
              </span>
            </div>
            <button
              onClick={() => logout()}
              title="Выйти"
              className="w-9 h-9 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 hover:border-white/20 flex items-center justify-center transition-all duration-200"
            >
              <LogOut size={15} className="text-white/60" />
            </button>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="relative z-10 flex-1 w-full max-w-6xl mx-auto px-4 md:px-6 py-12 md:py-16">
        {/* Welcome */}
        <div className="mb-12 animate-slide-in-down">
          <h1 className="text-3xl md:text-4xl font-bold text-white mb-2">
            Привет, {user?.name?.split(" ")[0] || "спортсмен"} 👋
          </h1>
          <p className="text-white/50">Выбери раздел чтобы начать</p>
        </div>

        {/* Cards grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          {CARDS.map((card, i) => {
            const Icon = card.icon;
            return (
              <button
                key={card.title}
                onClick={() => navigate(card.href)}
                className={`group relative text-left p-6 rounded-2xl border bg-gradient-to-br ${card.accent} ${card.border} ${card.shadow} backdrop-blur-sm hover:shadow-xl transition-all duration-300 hover:-translate-y-1 animate-slide-in-up`}
                style={{ animationDelay: `${i * 0.1}s` }}
              >
                <div className="flex items-start gap-4">
                  <div
                    className={`w-12 h-12 rounded-xl bg-gradient-to-br ${card.iconBg} border border-white/10 flex items-center justify-center flex-shrink-0 transition-transform duration-300 group-hover:scale-110`}
                  >
                    <Icon size={22} className={card.iconColor} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-lg font-bold text-white mb-1">
                      {card.title}
                    </h3>
                    <p className="text-sm text-white/50 leading-relaxed">
                      {card.desc}
                    </p>
                  </div>
                  <ChevronRight
                    size={18}
                    className="text-white/20 group-hover:text-white/60 group-hover:translate-x-1 transition-all duration-200 flex-shrink-0 mt-1"
                  />
                </div>
              </button>
            );
          })}
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-white/5 mt-auto">
        <div className="max-w-6xl mx-auto px-4 md:px-6 py-8">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <span className="text-white/20 text-sm">
                &copy; 2026 FitAgent.
              </span>
              <span className="text-white/20 text-sm">Все права защищены.</span>
            </div>

            <div className="flex items-center gap-6">
              <button className="text-xs text-white/30 hover:text-white/60 transition-colors">
                Политика конфиденциальности
              </button>
              <button className="text-xs text-white/30 hover:text-white/60 transition-colors">
                Условия использования
              </button>
            </div>

            <div className="flex items-center gap-3">
              <a
                href="#"
                aria-label="Instagram"
                className="w-8 h-8 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 flex items-center justify-center transition-all duration-200"
              >
                <Instagram size={14} className="text-white/40" />
              </a>
              <a
                href="#"
                aria-label="Twitter"
                className="w-8 h-8 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 flex items-center justify-center transition-all duration-200"
              >
                <Twitter size={14} className="text-white/40" />
              </a>
              <a
                href="#"
                aria-label="GitHub"
                className="w-8 h-8 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 flex items-center justify-center transition-all duration-200"
              >
                <Github size={14} className="text-white/40" />
              </a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
