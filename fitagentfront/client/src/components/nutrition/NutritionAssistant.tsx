import { useEffect, useRef, useState } from "react";
import {
  Bot,
  Send,
  X,
  PenSquare,
  ChevronDown,
  MessageSquare,
  Trash2,
} from "lucide-react";
import { trpc } from "@/lib/trpc";
import { toast } from "sonner";

const ASSISTANT_TITLE = "Nutrition Assistant";
const CONV_TITLE = "🥗 Ассистент по питанию";

const WELCOME_SUGGESTIONS = [
  "Чем заменить куриную грудку?",
  "Как набрать больше белка?",
  "Что съесть перед тренировкой?",
  "Разница между дефицитом и профицитом",
];

interface Message {
  id: number | string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function NutritionAssistant({ open, onClose }: Props) {
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [optimisticMessages, setOptimisticMessages] = useState<Message[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const utils = trpc.useUtils();

  const conversationsQuery = trpc.chat.getConversations.useQuery(undefined, {
    enabled: open,
  });

  // All nutrition conversations (by title prefix)
  const nutritionConvs = (conversationsQuery.data ?? []).filter(
    c =>
      c.title.includes("питанию") ||
      c.title.includes("Nutrition") ||
      c.title.startsWith("🥗")
  );

  const messagesQuery = trpc.chat.getMessages.useQuery(
    { conversationId: conversationId! },
    { enabled: conversationId !== null }
  );

  const createConv = trpc.chat.createConversation.useMutation({
    onSuccess: data => {
      setConversationId(data.conversationId);
      setShowHistory(false);
      utils.chat.getConversations.invalidate();
    },
    onError: () => toast.error("Не удалось создать чат"),
  });

  const sendMsg = trpc.chat.sendMessage.useMutation({
    onSuccess: () => {
      utils.chat.getMessages.invalidate({ conversationId: conversationId! });
      utils.chat.getConversations.invalidate();
      setOptimisticMessages([]);
    },
    onError: err => {
      toast.error(err.message || "Ошибка отправки");
      setOptimisticMessages([]);
      setIsSending(false);
    },
  });

  const deleteConv = trpc.chat.deleteConversation.useMutation({
    onSuccess: (_, { conversationId: deletedId }) => {
      utils.chat.getConversations.invalidate();
      if (conversationId === deletedId) {
        // Switch to the next available nutrition chat, or create fresh
        const remaining = nutritionConvs.filter(c => c.id !== deletedId);
        if (remaining.length > 0) {
          setConversationId(remaining[0].id);
        } else {
          setConversationId(null);
          createConv.mutate({ title: CONV_TITLE });
        }
        setOptimisticMessages([]);
        setInput("");
      }
    },
    onError: () => toast.error("Не удалось удалить чат"),
  });

  // On open: find the most recent nutrition conversation or create one.
  // If there's an empty draft (title still CONV_TITLE and no messages), reuse it.
  useEffect(() => {
    if (!open) return;
    if (!conversationsQuery.data) return;
    if (conversationId !== null) return; // already have one

    const existing = conversationsQuery.data.find(
      c =>
        c.title.includes("питанию") ||
        c.title.includes("Nutrition") ||
        c.title.startsWith("🥗")
    );
    if (existing) {
      setConversationId(existing.id);
    } else {
      createConv.mutate({ title: CONV_TITLE });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, conversationsQuery.data]);

  function handleNewChat() {
    // Reuse existing empty (untitled) nutrition chat instead of creating a new one
    const emptyDraft = nutritionConvs.find(c => c.title === CONV_TITLE);
    if (emptyDraft) {
      setConversationId(emptyDraft.id);
      setOptimisticMessages([]);
      setInput("");
      setShowHistory(false);
      return;
    }
    setConversationId(null);
    setOptimisticMessages([]);
    setInput("");
    setShowHistory(false);
    createConv.mutate({ title: CONV_TITLE });
  }

  function handleSelectConv(id: number) {
    setConversationId(id);
    setOptimisticMessages([]);
    setInput("");
    setShowHistory(false);
  }

  // Focus input when panel opens
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 300);
    }
  }, [open]);

  // Scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messagesQuery.data, optimisticMessages, isSending]);

  async function handleSend(text?: string) {
    const message = (text ?? input).trim();
    if (!message || !conversationId || isSending) return;

    setInput("");
    setIsSending(true);

    const optimistic: Message = {
      id: `opt-${Date.now()}`,
      role: "user",
      content: message,
      created_at: new Date().toISOString(),
    };
    setOptimisticMessages([optimistic]);

    await sendMsg.mutateAsync({ conversationId, message });
    setIsSending(false);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const allMessages: Message[] = [
    ...((messagesQuery.data ?? []).filter(
      m => m.role === "user" || m.role === "assistant"
    ) as Message[]),
    ...optimisticMessages,
  ];

  const isEmpty =
    !messagesQuery.isLoading && allMessages.length === 0 && !isSending;

  return (
    <>
      {/* Backdrop (mobile only) */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm md:hidden"
          onClick={onClose}
        />
      )}

      {/* Sliding panel */}
      <div
        className={[
          "fixed top-0 left-0 z-50 h-full w-full max-w-sm",
          "bg-[#0f0a1e]/95 border-r border-white/[0.08] flex flex-col",
          "shadow-[4px_0_40px_rgba(0,0,0,0.6)]",
          "transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
          open ? "translate-x-0" : "-translate-x-full",
        ].join(" ")}
      >
        {/* Header */}
        <div className="border-b border-white/[0.06] bg-[#0f0a1e]/80 backdrop-blur-md">
          <div className="flex items-center gap-3 px-4 py-3">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-purple-500/30 to-violet-600/20 border border-purple-500/30 flex items-center justify-center flex-shrink-0">
              <Bot size={16} className="text-purple-300" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-white truncate">
                {ASSISTANT_TITLE}
              </p>
              <p className="text-[11px] text-white/30">
                RAG · на основе науки о питании
              </p>
            </div>
            {/* New chat */}
            <button
              onClick={handleNewChat}
              disabled={createConv.isPending}
              title="Новый чат"
              className="w-7 h-7 rounded-lg bg-white/[0.04] border border-white/[0.07] flex items-center justify-center text-white/40 hover:text-purple-300 hover:bg-purple-500/10 hover:border-purple-500/30 transition-all disabled:opacity-40"
            >
              <PenSquare size={13} />
            </button>
            {/* History toggle */}
            {nutritionConvs.length > 1 && (
              <button
                onClick={() => setShowHistory(v => !v)}
                title="История чатов"
                className={[
                  "w-7 h-7 rounded-lg border flex items-center justify-center transition-all",
                  showHistory
                    ? "bg-purple-500/20 border-purple-500/40 text-purple-300"
                    : "bg-white/[0.04] border-white/[0.07] text-white/40 hover:text-white hover:bg-white/[0.09]",
                ].join(" ")}
              >
                <ChevronDown
                  size={13}
                  className={`transition-transform duration-200 ${showHistory ? "rotate-180" : ""}`}
                />
              </button>
            )}
            <button
              onClick={onClose}
              className="w-7 h-7 rounded-lg bg-white/[0.04] border border-white/[0.07] flex items-center justify-center text-white/40 hover:text-white hover:bg-white/[0.09] transition-all"
            >
              <X size={14} />
            </button>
          </div>

          {/* Conversation history list */}
          {showHistory && (
            <div className="px-3 pb-3 space-y-1">
              {nutritionConvs.map(c => (
                <div
                  key={c.id}
                  className={[
                    "group flex items-center gap-2 px-3 py-2 rounded-xl transition-all",
                    c.id === conversationId
                      ? "bg-purple-500/15 border border-purple-500/30"
                      : "bg-white/[0.03] border border-white/[0.06] hover:bg-white/[0.07]",
                  ].join(" ")}
                >
                  <button
                    onClick={() => handleSelectConv(c.id)}
                    className="flex items-center gap-2 flex-1 min-w-0 text-left"
                  >
                    <MessageSquare
                      size={12}
                      className="flex-shrink-0 text-purple-400/70"
                    />
                    <span
                      className={`text-xs truncate ${c.id === conversationId ? "text-white" : "text-white/60 group-hover:text-white"}`}
                    >
                      {c.title}
                    </span>
                  </button>
                  <button
                    onClick={() => deleteConv.mutate({ conversationId: c.id })}
                    disabled={deleteConv.isPending}
                    className="flex-shrink-0 w-5 h-5 flex items-center justify-center text-white/20 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all disabled:opacity-30"
                  >
                    <Trash2 size={11} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-white/10">
          {messagesQuery.isLoading || createConv.isPending ? (
            <div className="flex items-center justify-center h-32">
              <div className="flex gap-1.5">
                {[0, 1, 2].map(i => (
                  <div
                    key={i}
                    className="w-2 h-2 bg-purple-400/50 rounded-full animate-bounce"
                    style={{ animationDelay: `${i * 0.15}s` }}
                  />
                ))}
              </div>
            </div>
          ) : isEmpty ? (
            <div className="flex flex-col items-center gap-5 py-8 text-center">
              <div className="relative">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-purple-500/20 to-violet-600/10 border border-purple-500/20 flex items-center justify-center">
                  <Bot size={24} className="text-purple-300" />
                </div>
                <div className="absolute inset-0 rounded-2xl blur-xl bg-purple-500/10" />
              </div>
              <div>
                <p className="text-sm font-semibold text-white mb-1">
                  Привет! Я ваш нутри-ассистент
                </p>
                <p className="text-xs text-white/35 leading-relaxed max-w-[220px]">
                  Задайте любой вопрос о питании — я отвечу на основе научной
                  базы знаний
                </p>
              </div>
              {/* Suggestion chips */}
              <div className="flex flex-col gap-2 w-full">
                {WELCOME_SUGGESTIONS.map(s => (
                  <button
                    key={s}
                    onClick={() => handleSend(s)}
                    className="text-left px-3 py-2 rounded-xl bg-white/[0.04] border border-white/[0.07] text-xs text-white/60 hover:text-white hover:bg-purple-500/10 hover:border-purple-500/30 transition-all duration-150"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            allMessages.map(msg => <MessageBubble key={msg.id} msg={msg} />)
          )}

          {/* Typing indicator */}
          {isSending && !sendMsg.isPending && (
            <div className="flex justify-start">
              <div className="px-3 py-2.5 rounded-2xl rounded-tl-sm bg-white/[0.05] border border-white/[0.06]">
                <div className="flex gap-1">
                  {[0, 1, 2].map(i => (
                    <div
                      key={i}
                      className="w-1.5 h-1.5 bg-purple-400/60 rounded-full animate-bounce"
                      style={{ animationDelay: `${i * 0.15}s` }}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}
          {sendMsg.isPending && (
            <div className="flex justify-start">
              <div className="px-3 py-2.5 rounded-2xl rounded-tl-sm bg-white/[0.05] border border-white/[0.06]">
                <div className="flex gap-1">
                  {[0, 1, 2].map(i => (
                    <div
                      key={i}
                      className="w-1.5 h-1.5 bg-purple-400/60 rounded-full animate-bounce"
                      style={{ animationDelay: `${i * 0.15}s` }}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="px-4 py-4 border-t border-white/[0.06] bg-[#0f0a1e]/60">
          <div className="flex gap-2 items-end">
            <input
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isSending || !conversationId}
              placeholder="Спросите о питании..."
              className="flex-1 bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-sm text-white placeholder:text-white/25 focus:outline-none focus:border-purple-500/50 transition-colors disabled:opacity-50"
            />
            <button
              onClick={() => handleSend()}
              disabled={!input.trim() || isSending || !conversationId}
              className="w-9 h-9 flex-shrink-0 rounded-xl bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center text-white transition-all duration-150 active:scale-95"
            >
              <Send size={14} />
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={[
          "max-w-[85%] px-3 py-2.5 text-sm leading-relaxed rounded-2xl",
          isUser
            ? "bg-purple-600/30 border border-purple-500/40 text-white rounded-tr-sm"
            : "bg-white/[0.05] border border-white/[0.07] text-white/90 rounded-tl-sm",
        ].join(" ")}
      >
        <p className="whitespace-pre-wrap break-words">{msg.content}</p>
        <p
          className={`text-[10px] mt-1 ${isUser ? "text-purple-300/50" : "text-white/25"}`}
        >
          {new Date(msg.created_at).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </p>
      </div>
    </div>
  );
}

/** Floating trigger button to open the assistant */
export function NutritionAssistantFAB({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      title="Открыть ассистента по питанию"
      className="fixed bottom-6 left-6 z-40 w-12 h-12 rounded-2xl bg-purple-600 hover:bg-purple-500 border border-purple-500/50 shadow-[0_4px_20px_rgba(168,85,247,0.5)] hover:shadow-[0_4px_28px_rgba(168,85,247,0.65)] flex items-center justify-center text-white transition-all duration-200 active:scale-95"
    >
      <Bot size={20} />
    </button>
  );
}
