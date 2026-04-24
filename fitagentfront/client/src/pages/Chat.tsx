import { useAuth } from "@/_core/hooks/useAuth";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { trpc } from "@/lib/trpc";
import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import {
  Send,
  Plus,
  MessageSquare,
  ArrowLeft,
  Home,
  HelpCircle,
  Copy,
  Check,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { useLocation } from "wouter";

const QUICK_ACTIONS = [
  { icon: "🍽️", text: "Что я ел сегодня?" },
  { icon: "⚖️", text: "Запиши мой вес" },
  { icon: "✅", text: "Отметить тренировку как выполненную" },
  { icon: "📋", text: "Составь план питания на сегодня" },
];

function daysDeclension(n: number): string {
  if (n % 10 === 1 && n % 100 !== 11) return "день";
  if ([2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100))
    return "дня";
  return "дней";
}

function getTimeBasedHints(
  streak: number
): Array<{ icon: string; text: string }> {
  const hour = new Date().getHours();
  const streakHint =
    streak >= 2
      ? {
          icon: "🔥",
          text: `Ты активен ${streak} ${daysDeclension(streak)} подряд. Продолжим?`,
        }
      : { icon: "🌅", text: "Начни день правильно — составь план на сегодня" };

  if (hour >= 5 && hour < 10) {
    return [
      streakHint,
      { icon: "🥣", text: "Что съесть на завтрак?" },
      { icon: "📊", text: "Сколько калорий мне нужно сегодня?" },
      { icon: "💪", text: "Составь утреннюю тренировку на 20 минут" },
    ];
  }
  if (hour >= 10 && hour < 15) {
    return [
      { icon: "🥗", text: "Что приготовить на обед?" },
      { icon: "💪", text: "Составь план тренировки на сегодня" },
      { icon: "📊", text: "Сколько белка мне нужно в день?" },
      { icon: "🧘", text: "Упражнения для растяжки на 10 минут" },
    ];
  }
  if (hour >= 15 && hour < 21) {
    return [
      { icon: "🍽️", text: "Что лучше съесть после тренировки?" },
      { icon: "🥩", text: "Что приготовить на ужин?" },
      { icon: "🔥", text: "Как ускорить метаболизм?" },
      { icon: "📈", text: "Покажи мой прогресс за неделю" },
    ];
  }
  return [
    { icon: "⚖️", text: "Запиши мой вес" },
    { icon: "😴", text: "Как улучшить сон для восстановления?" },
    { icon: "📋", text: "Составь план на завтра" },
    { icon: "🧘", text: "Как правильно восстанавливаться между тренировками?" },
  ];
}

// ── UC-4: Suggested replies by topic ─────────────────────────────────────────
function getSuggestedReplies(content: string): string[] | null {
  const c = content.toLowerCase();
  if (c.includes("тренировк") || c.includes("упражнен") || c.includes("программ") || c.includes("подход"))
    return ["Измени упражнение", "Добавь разминку", "Облегчи нагрузку"];
  if (c.includes("рецепт") || c.includes("блюд") || c.includes("приготов") || c.includes("ингредиент"))
    return ["Рассчитай КБЖУ", "Альтернатива без лактозы", "Добавить в дневник питания"];
  if (c.includes("калори") || c.includes("белок") || c.includes("питани") || c.includes("рацион"))
    return ["Что съесть прямо сейчас?", "Составь план питания на день", "Что я ел сегодня?"];
  if (c.includes("вес") || c.includes("прогресс") || c.includes("результ"))
    return ["Как ускорить прогресс?", "Скорректируй план", "Что изменить в питании?"];
  return null;
}

const DOCKER_STEPS = [
  {
    label: "1. Copy example env and fill in your keys",
    cmd: "cp .env.example .env",
  },
  {
    label: "2. Build and start all services",
    cmd: "docker compose up --build -d",
  },
  { label: "3. Verify services are running", cmd: "docker compose ps" },
  {
    label: "4. Check API health",
    cmd: "curl http://localhost:8000/api/health",
  },
  { label: "5. View logs", cmd: "docker compose logs -f api" },
];

// ── Component ─────────────────────────────────────────────────────────────────

export default function Chat() {
  const { user, isAuthenticated, loading } = useAuth();
  const [, navigate] = useLocation();

  const profileQuery = trpc.profile.get.useQuery(undefined, {
    enabled: isAuthenticated,
    retry: false,
  });
  const onboarded = profileQuery.data?.onboarding_completed ?? true;

  const progressQuery = trpc.progress.getSummary.useQuery(undefined, {
    enabled: isAuthenticated && onboarded,
    retry: false,
  });
  const streak = progressQuery.data?.streak ?? 0;

  const todayStr = new Date().toISOString().slice(0, 10);
  const todayNutrition = trpc.nutrition.getPlan.useQuery(
    { date: todayStr },
    { enabled: isAuthenticated && onboarded, retry: false }
  );
  const activeWorkout = trpc.workout.getActive.useQuery(undefined, {
    enabled: isAuthenticated && onboarded,
    retry: false,
  });

  const [selectedConversation, setSelectedConversation] = useState<
    number | null
  >(null);
  const [messageInput, setMessageInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const handleExit = () => navigate("/");

  const handleCopy = (text: string, index: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 1500);
  };

  const utils = trpc.useUtils();

  // Queries
  const conversations = trpc.chat.getConversations.useQuery(undefined, {
    enabled: isAuthenticated,
  });

  const messages = trpc.chat.getMessages.useQuery(
    { conversationId: selectedConversation! },
    { enabled: isAuthenticated && selectedConversation !== null }
  );

  // Mutations
  const sendMsg = trpc.chat.sendMessage.useMutation({
    onSuccess: () => {
      setMessageInput("");
      messages.refetch();
      conversations.refetch();
      utils.profile.get.invalidate();
    },
    onError: error => {
      toast.error(error.message || "Failed to send message");
      setIsLoading(false);
    },
  });

  const createConv = trpc.chat.createConversation.useMutation({
    onSuccess: data => {
      setSelectedConversation(data.conversationId);
      conversations.refetch();
    },
    onError: () => {
      toast.error("Failed to create conversation");
    },
  });

  const deleteConv = trpc.chat.deleteConversation.useMutation({
    onSuccess: (_, { conversationId: deletedId }) => {
      conversations.refetch();
      if (selectedConversation === deletedId) {
        const remaining = (conversations.data ?? []).filter(
          c => c.id !== deletedId
        );
        setSelectedConversation(remaining.length > 0 ? remaining[0].id : null);
      }
    },
    onError: () => toast.error("Не удалось удалить чат"),
  });

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.data]);

  // Redirect if not authenticated
  useEffect(() => {
    if (loading) return;
    if (!isAuthenticated) navigate("/");
  }, [isAuthenticated, loading, navigate]);

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!messageInput.trim() || !selectedConversation) return;
    setIsLoading(true);
    await sendMsg.mutateAsync({
      conversationId: selectedConversation,
      message: messageInput,
    });
    setIsLoading(false);
  };

  const handleNewConversation = async () => {
    if (selectedConversation && messages.data?.length === 0) {
      setSelectedConversation(null);
      return;
    }
    const emptyConv = (conversations.data ?? []).find(
      c => c.id !== selectedConversation && c.title === "Новый чат"
    );
    if (emptyConv) {
      setSelectedConversation(emptyConv.id);
      return;
    }
    await createConv.mutateAsync({});
  };

  const handleQuickAction = async (text: string) => {
    if (!selectedConversation || isLoading || sendMsg.isPending) return;
    setIsLoading(true);
    await sendMsg.mutateAsync({
      conversationId: selectedConversation,
      message: text,
    });
    setIsLoading(false);
  };

  const handleHintClick = async (text: string) => {
    const emptyConv = (conversations.data ?? []).find(
      c => c.title === "Новый чат"
    );
    if (emptyConv) {
      setSelectedConversation(emptyConv.id);
      setIsLoading(true);
      await sendMsg.mutateAsync({
        conversationId: emptyConv.id,
        message: text,
      });
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    const conv = await createConv.mutateAsync({});
    await sendMsg.mutateAsync({
      conversationId: (conv as any).conversationId,
      message: text,
    });
    setIsLoading(false);
  };

  if (loading || !isAuthenticated) return null;

  return (
    <div className="h-screen bg-gradient-dark relative overflow-hidden flex">
      {/* Background orbs */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-gradient-to-br from-purple-600 to-purple-800 rounded-full blur-3xl opacity-10 animate-float" />
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-gradient-to-br from-cyan-500 to-purple-600 rounded-full blur-3xl opacity-10 animate-float-reverse" />
      </div>

      {/* Sidebar */}
      <div className="w-64 glass border-r border-white/10 flex flex-col relative z-10">
        <div className="p-4 border-b border-white/10">
          <button
            onClick={handleNewConversation}
            disabled={createConv.isPending}
            className="w-full btn-primary flex items-center justify-center gap-2 text-sm"
          >
            <Plus size={18} />
            New Chat
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-1">
          {conversations.data?.map(conv => (
            <div
              key={conv.id}
              className={`group flex items-center gap-1 rounded-lg transition-all duration-200 ${
                selectedConversation === conv.id
                  ? "bg-purple-500/30 border border-purple-500/50"
                  : "hover:bg-white/5 border border-transparent"
              }`}
            >
              <button
                onClick={() => setSelectedConversation(conv.id)}
                className="flex-1 min-w-0 text-left p-3"
              >
                <div className="flex items-start gap-2">
                  <MessageSquare
                    size={16}
                    className="mt-0.5 flex-shrink-0 text-purple-400"
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-white truncate">{conv.title}</p>
                    <p className="text-xs text-muted-sm mt-0.5">
                      {new Date(conv.updated_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
              </button>
              <button
                onClick={() => deleteConv.mutate({ conversationId: conv.id })}
                disabled={deleteConv.isPending}
                title="Удалить чат"
                className="flex-shrink-0 mr-2 p-1.5 rounded-md text-white/20 hover:text-red-400 hover:bg-red-400/10 opacity-0 group-hover:opacity-100 transition-all duration-150 disabled:opacity-30"
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>

        <div className="p-4 border-t border-white/10 space-y-3">
          <p className="text-xs text-muted-sm truncate">
            {user?.name || user?.email}
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={handleExit}
              title="Back to home"
              className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm text-white/70 hover:text-white hover:bg-white/10 border border-white/10 hover:border-white/20 transition-all duration-200"
            >
              <Home size={15} />
              Exit
            </button>

            <Dialog>
              <DialogTrigger asChild>
                <button
                  title="Docker setup instructions"
                  className="p-2 rounded-lg text-white/50 hover:text-white hover:bg-white/10 border border-white/10 hover:border-white/20 transition-all duration-200"
                >
                  <HelpCircle size={15} />
                </button>
              </DialogTrigger>
              <DialogContent className="bg-gray-900/95 border-white/10 text-white max-w-lg">
                <DialogHeader>
                  <DialogTitle className="text-white flex items-center gap-2">
                    Docker Setup
                  </DialogTitle>
                </DialogHeader>
                <p className="text-sm text-white/60 mb-4">
                  Run FitAgent locally with Docker Compose — three commands get
                  you a fully working stack.
                </p>
                <div className="space-y-3">
                  {DOCKER_STEPS.map((step, i) => (
                    <div key={i} className="space-y-1">
                      <p className="text-xs text-white/50">{step.label}</p>
                      <div className="flex items-center gap-2 bg-black/40 rounded-lg px-3 py-2 border border-white/10">
                        <code className="flex-1 text-sm text-green-400 font-mono">
                          {step.cmd}
                        </code>
                        <button
                          onClick={() => handleCopy(step.cmd, i)}
                          className="text-white/40 hover:text-white/80 transition-colors flex-shrink-0"
                        >
                          {copiedIndex === i ? (
                            <Check size={14} className="text-green-400" />
                          ) : (
                            <Copy size={14} />
                          )}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col relative z-10">
        {selectedConversation ? (
          <>
            {/* Header */}
            <div className="glass border-b border-white/10 p-4 flex items-center gap-4">
              <button
                onClick={() => setSelectedConversation(null)}
                className="md:hidden p-2 hover:bg-white/10 rounded-lg transition-colors"
              >
                <ArrowLeft size={20} className="text-white" />
              </button>
              <div className="flex-1">
                <h2 className="text-lg font-bold text-white">Chat</h2>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {messages.isLoading ? (
                <div className="flex items-center justify-center h-full">
                  <div className="text-muted-sm">Загрузка...</div>
                </div>
              ) : (messages.data ?? []).length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full gap-4">
                  <MessageSquare size={48} className="text-purple-400/30" />
                  <p className="text-muted-sm">
                    Start a conversation with your AI trainer
                  </p>
                </div>
              ) : (() => {
                const msgList = messages.data ?? [];
                const lastAiIdx = msgList.reduce(
                  (last, m, i) => (m.role === "assistant" ? i : last),
                  -1
                );
                return msgList.map((msg, idx) => (
                  <div key={msg.id}>
                    <div
                      className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                    >
                      <div
                        className={`max-w-xs lg:max-w-md px-4 py-3 rounded-lg ${
                          msg.role === "user"
                            ? "bg-purple-500/30 border border-purple-500/50 text-white"
                            : "glass text-white"
                        }`}
                      >
                        <div className="text-sm leading-relaxed prose prose-invert prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0 prose-headings:my-2">
                          <ReactMarkdown>{msg.content}</ReactMarkdown>
                        </div>
                        <p className="text-xs text-muted-sm mt-2">
                          {new Date(msg.created_at).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </p>
                      </div>
                    </div>
                    {/* UC-4: Suggested replies after last AI message */}
                    {idx === lastAiIdx && !isLoading && (() => {
                      const replies = getSuggestedReplies(msg.content);
                      if (!replies) return null;
                      return (
                        <div className="flex gap-2 flex-wrap mt-2 ml-1">
                          {replies.map(reply => (
                            <button
                              key={reply}
                              type="button"
                              onClick={() => handleQuickAction(reply)}
                              disabled={sendMsg.isPending}
                              className="px-3 py-1.5 rounded-full border border-purple-500/30 bg-purple-500/10 text-xs text-purple-300 hover:bg-purple-500/20 hover:text-white transition-all duration-200 disabled:opacity-30"
                            >
                              {reply}
                            </button>
                          ))}
                        </div>
                      );
                    })()}
                  </div>
                ));
              })()}

              {isLoading && (
                <div className="flex justify-start">
                  <div className="glass px-4 py-3 rounded-lg">
                    <div className="flex gap-2">
                      <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" />
                      <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce delay-100" />
                      <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce delay-200" />
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="glass border-t border-white/10 p-4 space-y-2.5">
              {/* Quick Actions */}
              <div className="flex gap-2 overflow-x-auto pb-0.5 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
                {QUICK_ACTIONS.map(action => (
                  <button
                    key={action.text}
                    type="button"
                    onClick={() => handleQuickAction(action.text)}
                    disabled={isLoading || sendMsg.isPending}
                    className="flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/[0.06] border border-white/10 hover:bg-white/10 hover:border-purple-500/30 text-xs text-white/50 hover:text-white transition-all duration-200 disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    <span>{action.icon}</span>
                    <span>{action.text}</span>
                  </button>
                ))}
              </div>
              <form onSubmit={handleSendMessage} className="flex gap-3">
                <Input
                  type="text"
                  placeholder="Ask your AI trainer..."
                  value={messageInput}
                  onChange={e => setMessageInput(e.target.value)}
                  disabled={isLoading || sendMsg.isPending}
                  className="bg-white/10 border-white/20 text-white placeholder:text-white/40 flex-1"
                />
                <button
                  type="submit"
                  disabled={
                    isLoading || sendMsg.isPending || !messageInput.trim()
                  }
                  className="btn-primary p-3 rounded-xl flex items-center justify-center"
                >
                  <Send size={20} />
                </button>
              </form>
            </div>
          </>
        ) : (
          /* Empty state with hints */
          <div className="flex-1 flex flex-col items-center justify-center gap-8 px-6 py-10 max-w-2xl mx-auto w-full">
            <div className="text-center">
              <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-purple-500/20 to-purple-600/10 border border-purple-500/20 flex items-center justify-center mx-auto mb-4">
                <MessageSquare size={26} className="text-purple-400" />
              </div>
              {!onboarded ? (
                <>
                  <h2 className="text-2xl font-bold text-white mb-1">
                    Сначала заполни профиль
                  </h2>
                  <p className="text-white/40 text-sm">
                    Пройди короткий онбординг, чтобы тренер знал о тебе всё
                    необходимое
                  </p>
                </>
              ) : (
                <>
                  <h2 className="text-2xl font-bold text-white mb-1">
                    Чем могу помочь?
                  </h2>
                  <p className="text-white/40 text-sm">
                    Выбери тему или напиши свой вопрос
                  </p>
                </>
              )}
            </div>

            {/* UC-5: Today widget */}
            {onboarded && (activeWorkout.data || todayNutrition.data?.plan) && (
              <div className="grid grid-cols-2 gap-3 w-full">
                {activeWorkout.data && (
                  <button
                    onClick={() => handleHintClick("Какая тренировка у меня сегодня по программе?")}
                    disabled={createConv.isPending}
                    className="text-left p-4 rounded-xl bg-purple-500/10 border border-purple-500/20 hover:bg-purple-500/15 hover:border-purple-500/40 transition-all duration-200 disabled:opacity-40"
                  >
                    <p className="text-xs text-purple-400 font-medium mb-1">🏋️ Программа</p>
                    <p className="text-sm text-white font-semibold truncate">{activeWorkout.data.name}</p>
                    <p className="text-xs text-white/40 mt-0.5">
                      {activeWorkout.data.days_per_week} дн / неделю
                    </p>
                  </button>
                )}
                {todayNutrition.data?.plan ? (
                  <button
                    onClick={() => handleHintClick("Сколько калорий я уже съел сегодня?")}
                    disabled={createConv.isPending}
                    className="text-left p-4 rounded-xl bg-cyan-500/10 border border-cyan-500/20 hover:bg-cyan-500/15 hover:border-cyan-500/40 transition-all duration-200 disabled:opacity-40"
                  >
                    <p className="text-xs text-cyan-400 font-medium mb-1">🥗 Питание сегодня</p>
                    <p className="text-sm text-white font-semibold">
                      {Object.values(todayNutrition.data.plan.meals)
                        .flat()
                        .reduce((sum, item) => sum + item.calories, 0)
                        .toFixed(0)} ккал
                    </p>
                    <p className="text-xs text-white/40 mt-0.5">
                      цель: {todayNutrition.data.daily_norm?.target_calories ?? "—"} ккал
                    </p>
                  </button>
                ) : activeWorkout.data ? null : (
                  <button
                    onClick={() => handleHintClick("Составь мне план питания на сегодня")}
                    disabled={createConv.isPending}
                    className="text-left p-4 rounded-xl bg-white/[0.04] border border-white/[0.08] hover:bg-white/[0.08] transition-all duration-200 disabled:opacity-40"
                  >
                    <p className="text-xs text-white/40 font-medium mb-1">🥗 Питание</p>
                    <p className="text-sm text-white/60">Нет плана на сегодня</p>
                    <p className="text-xs text-purple-400 mt-0.5">Сгенерировать →</p>
                  </button>
                )}
              </div>
            )}

            {onboarded && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full">
                {getTimeBasedHints(streak).map(hint => (
                  <button
                    key={hint.text}
                    onClick={() => handleHintClick(hint.text)}
                    disabled={createConv.isPending}
                    className="flex items-center gap-3 px-4 py-3 rounded-xl bg-white/[0.04] border border-white/[0.08] hover:bg-white/[0.08] hover:border-purple-500/30 text-left text-sm text-white/70 hover:text-white transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <span className="text-lg flex-shrink-0">{hint.icon}</span>
                    <span className="leading-snug">{hint.text}</span>
                  </button>
                ))}
              </div>
            )}

            <button
              onClick={handleNewConversation}
              disabled={createConv.isPending}
              className="btn-primary flex items-center gap-2 text-sm"
            >
              <Plus size={16} />
              Начать новый чат
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
