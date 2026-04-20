import { useLocation } from "wouter";
import { ChevronLeft, Shield } from "lucide-react";

const LAST_UPDATED = "20 апреля 2026 г.";

const SECTIONS = [
  {
    title: "1. Общие положения",
    content: `Настоящая Политика конфиденциальности (далее — «Политика») описывает, какие персональные данные собирает и обрабатывает FitAgent (далее — «Сервис», «мы»), а также каким образом эти данные используются, хранятся и защищаются.

Используя Сервис, вы соглашаетесь с условиями данной Политики. Если вы не согласны с любым из её пунктов, пожалуйста, прекратите использование Сервиса.`,
  },
  {
    title: "2. Какие данные мы собираем",
    content: `**Данные профиля**, предоставляемые при регистрации через Google OAuth:
— имя и адрес электронной почты;
— фотография профиля (аватар Google).

**Данные о физических параметрах**, вводимые вами вручную:
— возраст, рост, вес, пол;
— уровень физической активности и цель (похудение, набор массы и т. д.);
— информация о травмах и ограничениях.

**Данные об активности в Сервисе**:
— история веса и тренировок;
— дневник питания и планы питания;
— сообщения в чате с AI-тренером;
— программы тренировок.

**Технические данные**:
— IP-адрес и информация об устройстве (браузер, ОС);
— файлы cookie, необходимые для работы аутентификации.`,
  },
  {
    title: "3. Как мы используем данные",
    content: `Собранные данные используются исключительно для:
— предоставления персонализированных рекомендаций по питанию и тренировкам;
— генерации планов питания и тренировок с помощью AI;
— хранения истории прогресса и дневника питания;
— обеспечения работы чата с AI-тренером;
— улучшения алгоритмов и качества Сервиса.

Мы не используем ваши данные в рекламных целях и не передаём их третьим лицам для маркетинга.`,
  },
  {
    title: "4. Передача данных третьим лицам",
    content: `Для обеспечения работы Сервиса мы взаимодействуем со следующими третьими сторонами:

**Google LLC** — аутентификация через OAuth 2.0. При входе Google передаёт нам ваше имя, email и аватар в соответствии с политикой конфиденциальности Google.

**Google Gemini API** — генерация планов питания и тренировок, ответы AI-тренера. Ваши запросы могут передаваться в API для получения ответа.

**Railway / облачная инфраструктура** — хостинг Сервиса и базы данных. Данные хранятся на защищённых серверах.

Мы не продаём, не сдаём в аренду и не обмениваем ваши персональные данные с какими-либо иными третьими лицами.`,
  },
  {
    title: "5. Хранение и защита данных",
    content: `Ваши данные хранятся в зашифрованной базе данных PostgreSQL. Доступ к базе данных ограничен и защищён паролем.

Сессии аутентификации защищены JWT-токенами с ограниченным сроком действия. Передача данных между клиентом и сервером осуществляется по протоколу HTTPS.

Мы храним ваши данные до момента удаления вашего аккаунта или до прекращения работы Сервиса.`,
  },
  {
    title: "6. Ваши права",
    content: `Вы имеете право в любое время:
— запросить копию хранимых о вас данных;
— потребовать исправления некорректных данных;
— потребовать удаления ваших данных («право на забвение»);
— отозвать согласие на обработку данных.

Для реализации этих прав свяжитесь с нами по адресу, указанному в разделе «Контакты».`,
  },
  {
    title: "7. Файлы cookie",
    content: `Сервис использует только технически необходимые файлы cookie:
— session cookie для поддержания вашей авторизации;
— cookie безопасности для защиты от CSRF-атак.

Мы не используем рекламные или аналитические файлы cookie третьих сторон.`,
  },
  {
    title: "8. Данные несовершеннолетних",
    content: `Сервис предназначен для лиц, достигших 16 лет. Мы сознательно не собираем данные детей до 16 лет. Если вам стало известно, что ребёнок предоставил нам свои данные без согласия родителей, пожалуйста, свяжитесь с нами — мы удалим такие данные.`,
  },
  {
    title: "9. Изменения в Политике",
    content: `Мы оставляем за собой право обновлять данную Политику. При внесении существенных изменений мы уведомим вас через интерфейс Сервиса или по электронной почте. Дата последнего обновления всегда указана в начале документа.`,
  },
  {
    title: "10. Контакты",
    content: `По вопросам, связанным с обработкой персональных данных, вы можете обратиться к нам:

Email: privacy@fitagent.app
Telegram: @Xariello

Мы ответим в течение 5 рабочих дней.`,
  },
];

export default function Privacy() {
  const [, navigate] = useLocation();

  return (
    <div className="min-h-screen bg-[#0b0817] relative overflow-hidden">
      {/* Ambient */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none select-none">
        <div className="absolute -top-60 -right-60 w-[500px] h-[500px] bg-purple-700 rounded-full blur-[160px] opacity-[0.06]" />
        <div className="absolute -bottom-40 -left-40 w-[400px] h-[400px] bg-indigo-700 rounded-full blur-[140px] opacity-[0.05]" />
      </div>

      {/* Header */}
      <header className="relative z-10 w-full border-b border-white/[0.05] bg-[#0b0817]/80 backdrop-blur-md sticky top-0">
        <div className="max-w-3xl mx-auto px-4 md:px-6 py-4 flex items-center gap-3">
          <button
            onClick={() => navigate(-1 as unknown as string)}
            className="w-9 h-9 rounded-xl bg-white/[0.05] border border-white/[0.08] hover:bg-white/[0.09] flex items-center justify-center text-white/50 hover:text-white transition-all"
          >
            <ChevronLeft size={18} />
          </button>
          <div className="w-8 h-8 rounded-xl bg-purple-500/20 border border-purple-500/25 flex items-center justify-center">
            <Shield size={15} className="text-purple-300" />
          </div>
          <h1 className="text-base font-bold text-white">
            Политика конфиденциальности
          </h1>
        </div>
      </header>

      {/* Content */}
      <main className="relative z-10 max-w-3xl mx-auto px-4 md:px-6 py-10 pb-20">
        {/* Intro card */}
        <div className="rounded-2xl bg-purple-500/[0.07] border border-purple-500/20 p-6 mb-8">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-xl bg-purple-500/20 border border-purple-500/25 flex items-center justify-center flex-shrink-0 mt-0.5">
              <Shield size={18} className="text-purple-300" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white mb-1">
                Ваша конфиденциальность важна для нас
              </h2>
              <p className="text-sm text-white/50 leading-relaxed">
                FitAgent собирает только данные, необходимые для работы Сервиса.
                Мы не продаём ваши данные и не передаём их рекламным сетям.
              </p>
              <p className="text-xs text-white/30 mt-3">
                Последнее обновление: {LAST_UPDATED}
              </p>
            </div>
          </div>
        </div>

        {/* Sections */}
        <div className="space-y-8">
          {SECTIONS.map(section => (
            <section key={section.title}>
              <h2 className="text-base font-bold text-white mb-3 pb-2 border-b border-white/[0.06]">
                {section.title}
              </h2>
              <div className="text-sm text-white/55 leading-relaxed whitespace-pre-line space-y-2">
                {section.content.split("\n").map((line, i) => {
                  // Bold markdown-like **text**
                  const parts = line.split(/(\*\*[^*]+\*\*)/g);
                  return (
                    <p key={i} className={line.startsWith("—") ? "pl-3" : ""}>
                      {parts.map((part, j) =>
                        part.startsWith("**") && part.endsWith("**") ? (
                          <span key={j} className="text-white/80 font-medium">
                            {part.slice(2, -2)}
                          </span>
                        ) : (
                          part
                        )
                      )}
                    </p>
                  );
                })}
              </div>
            </section>
          ))}
        </div>

        {/* Footer nav */}
        <div className="mt-12 pt-6 border-t border-white/[0.06] flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="text-xs text-white/25">
            © 2026 FitAgent. Все права защищены.
          </p>
          <div className="flex gap-4">
            <button
              onClick={() => navigate("/terms")}
              className="text-xs text-purple-400 hover:text-purple-300 transition-colors"
            >
              Условия использования →
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
