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

const DOCKER_STEPS = [
  {
    label: "1. Copy example env and fill in your keys",
    cmd: "cp .env.example .env",
  },
  {
    label: "2. Build and start all services",
    cmd: "docker compose up --build -d",
  },
  {
    label: "3. Verify services are running",
    cmd: "docker compose ps",
  },
  {
    label: "4. Check API health",
    cmd: "curl http://localhost:8000/api/health",
  },
  {
    label: "5. View logs",
    cmd: "docker compose logs -f api",
  },
];

export default function Chat() {
  const { user, isAuthenticated, loading } = useAuth();
  const [, navigate] = useLocation();
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

  // Queries
  const conversations = trpc.chat.getConversations.useQuery(undefined, {
    enabled: isAuthenticated,
  });

  const messages = trpc.chat.getMessages.useQuery(
    { conversationId: selectedConversation! },
    { enabled: isAuthenticated && selectedConversation !== null }
  );

  // Mutations
  const createConv = trpc.chat.createConversation.useMutation({
    onSuccess: data => {
      setSelectedConversation(data.conversationId);
      conversations.refetch();
    },
    onError: () => {
      toast.error("Failed to create conversation");
    },
  });

  const sendMsg = trpc.chat.sendMessage.useMutation({
    onSuccess: () => {
      setMessageInput("");
      messages.refetch();
      conversations.refetch();
    },
    onError: error => {
      toast.error(error.message || "Failed to send message");
      setIsLoading(false);
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

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.data]);

  // Redirect if not authenticated (wait for auth check to complete first)
  useEffect(() => {
    if (loading) return;
    if (!isAuthenticated) {
      navigate("/");
    }
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
    await createConv.mutateAsync({});
  };

  if (loading || !isAuthenticated) {
    return null;
  }

  return (
    <div className="h-screen bg-gradient-dark relative overflow-hidden flex">
      {/* Animated background orbs */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-gradient-to-br from-purple-600 to-purple-800 rounded-full blur-3xl opacity-10 animate-float"></div>
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-gradient-to-br from-cyan-500 to-purple-600 rounded-full blur-3xl opacity-10 animate-float-reverse"></div>
      </div>

      {/* Sidebar */}
      <div className="w-64 glass border-r border-white/10 flex flex-col relative z-10">
        {/* Header */}
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

        {/* Conversations List */}
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

        {/* Sidebar Footer: user info + actions */}
        <div className="p-4 border-t border-white/10 space-y-3">
          {/* User name */}
          <p className="text-xs text-muted-sm truncate">
            {user?.name || user?.email}
          </p>

          {/* Action buttons */}
          <div className="flex items-center gap-2">
            {/* Exit → home */}
            <button
              onClick={handleExit}
              title="Back to home"
              className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm text-white/70 hover:text-white hover:bg-white/10 border border-white/10 hover:border-white/20 transition-all duration-200"
            >
              <Home size={15} />
              Exit
            </button>

            {/* Docker setup dialog */}
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
                    🐳 Docker Setup
                  </DialogTitle>
                </DialogHeader>

                <p className="text-sm text-white/60 mb-4">
                  Run FitAgent locally with Docker Compose — three commands get
                  you a fully working stack (PostgreSQL · FastAPI · React).
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
                          title="Copy command"
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

                <div className="mt-4 p-3 bg-purple-500/10 border border-purple-500/20 rounded-lg">
                  <p className="text-xs text-purple-300">
                    <strong>Requires:</strong> Docker Desktop, a Gemini API key,
                    and Google OAuth credentials. Copy{" "}
                    <code className="bg-black/30 px-1 rounded">
                      .env.example → .env
                    </code>{" "}
                    and fill in the values before running.
                  </p>
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
            {/* Chat Header */}
            <div className="glass border-b border-white/10 p-4 flex items-center gap-4">
              <button
                onClick={() => setSelectedConversation(null)}
                className="md:hidden p-2 hover:bg-white/10 rounded-lg transition-colors"
              >
                <ArrowLeft size={20} className="text-white" />
              </button>
              <h2 className="text-lg font-bold text-white flex-1">Chat</h2>
            </div>

            {/* Messages Area */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {messages.isLoading ? (
                <div className="flex items-center justify-center h-full">
                  <div className="text-muted-sm">Loading messages...</div>
                </div>
              ) : messages.data && messages.data.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full gap-4">
                  <MessageSquare size={48} className="text-purple-400/30" />
                  <p className="text-muted-sm">
                    Start a conversation with your AI trainer
                  </p>
                </div>
              ) : (
                messages.data?.map(msg => (
                  <div
                    key={msg.id}
                    className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-xs lg:max-w-md px-4 py-3 rounded-lg ${
                        msg.role === "user"
                          ? "bg-purple-500/30 border border-purple-500/50 text-white"
                          : "glass text-white"
                      }`}
                    >
                      <p className="text-sm leading-relaxed">{msg.content}</p>
                      <p className="text-xs text-muted-sm mt-2">
                        {new Date(msg.created_at).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </p>
                    </div>
                  </div>
                ))
              )}
              {isLoading && (
                <div className="flex justify-start">
                  <div className="glass px-4 py-3 rounded-lg">
                    <div className="flex gap-2">
                      <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce"></div>
                      <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce delay-100"></div>
                      <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce delay-200"></div>
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input Area */}
            <div className="glass border-t border-white/10 p-4">
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
          <div className="flex-1 flex flex-col items-center justify-center gap-6">
            <MessageSquare size={64} className="text-purple-400/30" />
            <div className="text-center">
              <h2 className="text-2xl font-bold text-white mb-2">
                Welcome to FitAgent Chat
              </h2>
              <p className="text-muted-sm mb-6">
                Start a new conversation to get personalized fitness and
                nutrition advice
              </p>
              <button
                onClick={handleNewConversation}
                disabled={createConv.isPending}
                className="btn-primary"
              >
                Start New Chat
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
