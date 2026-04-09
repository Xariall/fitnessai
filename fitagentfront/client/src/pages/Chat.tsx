import { useAuth } from "@/_core/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { trpc } from "@/lib/trpc";
import { useState, useEffect, useRef } from "react";
import { Send, Plus, MessageSquare, ArrowLeft } from "lucide-react";
import { toast } from "sonner";
import { useLocation } from "wouter";

export default function Chat() {
  const { user, isAuthenticated } = useAuth();
  const [, navigate] = useLocation();
  const [selectedConversation, setSelectedConversation] = useState<number | null>(null);
  const [messageInput, setMessageInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

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
    onSuccess: (data) => {
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
    onError: (error) => {
      toast.error(error.message || "Failed to send message");
      setIsLoading(false);
    },
  });

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.data]);

  // Redirect if not authenticated
  useEffect(() => {
    if (!isAuthenticated) {
      navigate("/");
    }
  }, [isAuthenticated, navigate]);

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

  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gradient-dark relative overflow-hidden flex">
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
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {conversations.data?.map((conv) => (
            <button
              key={conv.id}
              onClick={() => setSelectedConversation(conv.id)}
              className={`w-full text-left p-3 rounded-lg transition-all duration-300 ${
                selectedConversation === conv.id
                  ? "bg-purple-500/30 border border-purple-500/50"
                  : "hover:bg-white/5 border border-transparent"
              }`}
            >
              <div className="flex items-start gap-2">
                <MessageSquare size={16} className="mt-1 flex-shrink-0 text-purple-400" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-white truncate">{conv.title}</p>
                  <p className="text-xs text-muted-sm mt-1">
                    {new Date(conv.updated_at).toLocaleDateString()}
                  </p>
                </div>
              </div>
            </button>
          ))}
        </div>

        {/* User Info */}
        <div className="p-4 border-t border-white/10">
          <div className="text-sm text-muted-sm">
            <p className="truncate">{user?.name || user?.email}</p>
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
                  <p className="text-muted-sm">Start a conversation with your AI trainer</p>
                </div>
              ) : (
                messages.data?.map((msg) => (
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
                  onChange={(e) => setMessageInput(e.target.value)}
                  disabled={isLoading || sendMsg.isPending}
                  className="bg-white/10 border-white/20 text-white placeholder:text-white/40 flex-1"
                />
                <button
                  type="submit"
                  disabled={isLoading || sendMsg.isPending || !messageInput.trim()}
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
              <h2 className="text-2xl font-bold text-white mb-2">Welcome to FitAgent Chat</h2>
              <p className="text-muted-sm mb-6">Start a new conversation to get personalized fitness and nutrition advice</p>
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
