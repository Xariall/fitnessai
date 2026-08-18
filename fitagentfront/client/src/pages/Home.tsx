import { ChevronRight, Clock, Target, TrendingUp } from "lucide-react";

const TELEGRAM_BOT_URL = "https://t.me/voidFitbot";

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-dark relative overflow-hidden">
      {/* Animated background orbs */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-gradient-to-br from-purple-600 to-purple-800 rounded-full blur-3xl opacity-10 animate-float"></div>
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-gradient-to-br from-cyan-500 to-purple-600 rounded-full blur-3xl opacity-10 animate-float-reverse"></div>
      </div>

      {/* Content */}
      <div className="relative z-10">
        {/* Header */}
        <header className="w-full max-w-6xl mx-auto px-4 md:px-6 py-6 md:py-8 flex justify-between items-center animate-slide-in-down">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-purple-500/50">
              <svg
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="none"
                stroke="white"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M6.5 6.5h11M6.5 17.5h11M4 9.5v5M20 9.5v5M2 11v2M22 11v2" />
              </svg>
            </div>
            <span className="text-xl font-bold text-white">FitAgent</span>
          </div>
          <a
            href={TELEGRAM_BOT_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-medium text-white/70 hover:text-white transition-colors flex items-center gap-1"
          >
            Открыть бота <ChevronRight size={16} />
          </a>
        </header>

        {/* Main Content */}
        <main className="w-full max-w-6xl mx-auto px-4 md:px-6">
          {/* Hero Section */}
          <div className="text-center mt-16 md:mt-24 mb-8 animate-slide-in-down delay-100">
            <h1 className="text-5xl md:text-7xl font-bold mb-6 leading-tight text-white">
              Твой AI тренер
              <br />
              <span className="gradient-text">и диетолог</span>
            </h1>
            <p className="text-muted text-lg md:text-xl max-w-2xl mx-auto leading-relaxed">
              Персональный план тренировок и питания прямо в Telegram.
              Адаптируется под тебя каждую неделю.
            </p>
          </div>

          {/* Primary CTA */}
          <div className="flex flex-col items-center gap-4 mb-20 md:mb-32 animate-slide-in-up delay-200">
            <a
              href={TELEGRAM_BOT_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-primary"
            >
              Начать в Telegram
            </a>
          </div>

          {/* Features Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full mb-24 md:mb-32">
            {/* Card 1 - План под тебя */}
            <div className="glass card-hover p-8 rounded-2xl text-left flex flex-col gap-5 animate-slide-in-up delay-200">
              <div className="icon-box group-hover:from-purple-500/40 group-hover:to-cyan-500/40">
                <Target size={24} className="text-purple-300" />
              </div>
              <div>
                <h3 className="font-bold text-lg mb-2 text-white">
                  План под тебя
                </h3>
                <p className="text-muted-sm text-sm leading-relaxed">
                  Учитывает цель, уровень и оборудование
                </p>
              </div>
            </div>

            {/* Card 2 - Дневник питания */}
            <div className="glass card-hover p-8 rounded-2xl text-left flex flex-col gap-5 animate-slide-in-up delay-300">
              <div className="icon-box group-hover:from-purple-500/40 group-hover:to-cyan-500/40">
                <Clock size={24} className="text-cyan-300" />
              </div>
              <div>
                <h3 className="font-bold text-lg mb-2 text-white">
                  Дневник питания
                </h3>
                <p className="text-muted-sm text-sm leading-relaxed">
                  Трекинг КБЖУ через чат, фото или текст
                </p>
              </div>
            </div>

            {/* Card 3 - Прогресс */}
            <div className="glass card-hover p-8 rounded-2xl text-left flex flex-col gap-5 animate-slide-in-up delay-400">
              <div className="icon-box group-hover:from-purple-500/40 group-hover:to-cyan-500/40">
                <TrendingUp size={24} className="text-purple-300" />
              </div>
              <div>
                <h3 className="font-bold text-lg mb-2 text-white">Прогресс</h3>
                <p className="text-muted-sm text-sm leading-relaxed">
                  Замеры, вес и адаптация плана
                </p>
              </div>
            </div>
          </div>

          {/* Separator */}
          <div className="h-px bg-gradient-to-r from-transparent via-white/10 to-transparent mb-24 md:mb-32 animate-fade-in delay-400"></div>

          {/* How It Works Section */}
          <div className="w-full mb-32 md:mb-40 animate-slide-in-up delay-400">
            <h2 className="text-2xl md:text-3xl font-bold text-center mb-20 text-white">
              Как это работает
            </h2>

            <div className="relative flex flex-col md:flex-row justify-between items-start gap-12 md:gap-8">
              {/* Connecting line (desktop only) */}
              <div className="hidden md:block absolute top-6 left-0 w-full h-px bg-gradient-to-r from-transparent via-purple-500/30 to-transparent -z-10"></div>

              {/* Step 1 */}
              <div className="flex flex-col items-center text-center w-full md:w-1/3">
                <div className="step-circle mb-6">1</div>
                <h4 className="font-bold text-lg mb-3 text-white">
                  Открой бота
                </h4>
                <p className="text-muted-sm text-sm">
                  Расскажи цель, параметры, условия
                </p>
              </div>

              {/* Step 2 */}
              <div className="flex flex-col items-center text-center w-full md:w-1/3">
                <div className="step-circle mb-6">2</div>
                <h4 className="font-bold text-lg mb-3 text-white">
                  Получи план
                </h4>
                <p className="text-muted-sm text-sm">Тренировки + питание</p>
              </div>

              {/* Step 3 */}
              <div className="flex flex-col items-center text-center w-full md:w-1/3">
                <div className="step-circle mb-6">3</div>
                <h4 className="font-bold text-lg mb-3 text-white">
                  Следуй и расти
                </h4>
                <p className="text-muted-sm text-sm">Бот адаптирует план</p>
              </div>
            </div>
          </div>

          {/* Bottom CTA Section */}
          <div className="glass p-8 md:p-16 rounded-3xl flex flex-col items-center gap-8 mb-20 animate-slide-in-up delay-500">
            <div>
              <h2 className="text-3xl md:text-4xl font-bold text-center text-white">
                Готов начать?
              </h2>
            </div>
            <a
              href={TELEGRAM_BOT_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-primary flex items-center gap-2"
            >
              Открыть {TELEGRAM_BOT_URL.replace("https://t.me/", "@")}
              <ChevronRight size={18} />
            </a>
          </div>
        </main>

        {/* Footer */}
        <footer className="text-center text-muted-sm text-xs py-8 border-t border-white/5 flex flex-col items-center gap-2">
          <div className="flex gap-4">
            <a
              href="/privacy"
              className="hover:text-white/70 transition-colors"
            >
              Конфиденциальность
            </a>
            <a href="/terms" className="hover:text-white/70 transition-colors">
              Условия использования
            </a>
          </div>
          &copy; 2026 FitAgent. Все права защищены.
        </footer>
      </div>
    </div>
  );
}
