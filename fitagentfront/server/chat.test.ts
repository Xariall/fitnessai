import { describe, expect, it, beforeEach, vi } from "vitest";
import { appRouter } from "./routers";
import type { TrpcContext } from "./_core/context";

// Mock database functions
vi.mock("./db", () => ({
  createConversation: vi.fn(),
  getConversationsByUserId: vi.fn(),
  getConversationById: vi.fn(),
  addMessage: vi.fn(),
  getMessagesByConversationId: vi.fn(),
  updateConversationTitle: vi.fn(),
}));

// Mock LLM
vi.mock("./_core/llm", () => ({
  invokeLLM: vi.fn(),
}));

import * as db from "./db";
import * as llm from "./_core/llm";

type AuthenticatedUser = NonNullable<TrpcContext["user"]>;

function createAuthContext(): { ctx: TrpcContext; user: AuthenticatedUser } {
  const user: AuthenticatedUser = {
    id: 1,
    openId: "test-user",
    email: "test@example.com",
    name: "Test User",
    loginMethod: "manus",
    role: "user",
    createdAt: new Date(),
    updatedAt: new Date(),
    lastSignedIn: new Date(),
  };

  const ctx: TrpcContext = {
    user,
    req: {
      protocol: "https",
      headers: {},
    } as TrpcContext["req"],
    res: {
      clearCookie: vi.fn(),
    } as unknown as TrpcContext["res"],
  };

  return { ctx, user };
}

describe("chat procedures", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("createConversation", () => {
    it("creates a new conversation for authenticated user", async () => {
      const { ctx, user } = createAuthContext();
      const caller = appRouter.createCaller(ctx);

      vi.mocked(db.createConversation).mockResolvedValue(undefined as any);
      vi.mocked(db.getConversationsByUserId).mockResolvedValue([
        {
          id: 1,
          userId: user.id,
          title: "New Conversation",
          createdAt: new Date(),
          updatedAt: new Date(),
        },
      ]);

      const result = await caller.chat.createConversation({
        title: "Test Chat",
      });

      expect(result.success).toBe(true);
      expect(result.conversationId).toBe(1);
      expect(db.createConversation).toHaveBeenCalledWith(user.id, "Test Chat");
    });
  });

  describe("getConversations", () => {
    it("returns user's conversations", async () => {
      const { ctx, user } = createAuthContext();
      const caller = appRouter.createCaller(ctx);

      const mockConversations = [
        {
          id: 1,
          userId: user.id,
          title: "Chat 1",
          createdAt: new Date(),
          updatedAt: new Date(),
        },
        {
          id: 2,
          userId: user.id,
          title: "Chat 2",
          createdAt: new Date(),
          updatedAt: new Date(),
        },
      ];

      vi.mocked(db.getConversationsByUserId).mockResolvedValue(mockConversations);

      const result = await caller.chat.getConversations();

      expect(result).toEqual(mockConversations);
      expect(db.getConversationsByUserId).toHaveBeenCalledWith(user.id);
    });
  });

  describe("getMessages", () => {
    it("returns messages for a conversation", async () => {
      const { ctx, user } = createAuthContext();
      const caller = appRouter.createCaller(ctx);

      const mockConversation = {
        id: 1,
        userId: user.id,
        title: "Test Chat",
        createdAt: new Date(),
        updatedAt: new Date(),
      };

      const mockMessages = [
        {
          id: 1,
          conversationId: 1,
          role: "user" as const,
          content: "Hello",
          createdAt: new Date(),
        },
        {
          id: 2,
          conversationId: 1,
          role: "assistant" as const,
          content: "Hi there!",
          createdAt: new Date(),
        },
      ];

      vi.mocked(db.getConversationById).mockResolvedValue(mockConversation);
      vi.mocked(db.getMessagesByConversationId).mockResolvedValue(mockMessages);

      const result = await caller.chat.getMessages({ conversationId: 1 });

      expect(result).toEqual(mockMessages);
      expect(db.getConversationById).toHaveBeenCalledWith(1, user.id);
      expect(db.getMessagesByConversationId).toHaveBeenCalledWith(1);
    });

    it("throws error if conversation not found", async () => {
      const { ctx } = createAuthContext();
      const caller = appRouter.createCaller(ctx);

      vi.mocked(db.getConversationById).mockResolvedValue(undefined);

      try {
        await caller.chat.getMessages({ conversationId: 999 });
        expect.fail("Should have thrown error");
      } catch (error: any) {
        expect(error.message).toContain("Conversation not found");
      }
    });
  });

  describe("sendMessage", () => {
    it("sends message and gets AI response", async () => {
      const { ctx, user } = createAuthContext();
      const caller = appRouter.createCaller(ctx);

      const mockConversation = {
        id: 1,
        userId: user.id,
        title: "Test Chat",
        createdAt: new Date(),
        updatedAt: new Date(),
      };

      const mockMessages = [
        {
          id: 1,
          conversationId: 1,
          role: "user" as const,
          content: "Hello",
          createdAt: new Date(),
        },
      ];

      vi.mocked(db.getConversationById).mockResolvedValue(mockConversation);
      vi.mocked(db.getMessagesByConversationId).mockResolvedValue(mockMessages);
      vi.mocked(db.addMessage).mockResolvedValue(undefined as any);
      vi.mocked(llm.invokeLLM).mockResolvedValue({
        choices: [
          {
            message: {
              content: "AI response",
            },
          },
        ],
      } as any);

      const result = await caller.chat.sendMessage({
        conversationId: 1,
        message: "Hello",
      });

      expect(result.success).toBe(true);
      expect(result.assistantMessage).toBe("AI response");
      expect(db.addMessage).toHaveBeenCalledWith(1, "user", "Hello");
      expect(db.addMessage).toHaveBeenCalledWith(1, "assistant", "AI response");
    });

    it("rejects empty messages", async () => {
      const { ctx } = createAuthContext();
      const caller = appRouter.createCaller(ctx);

      try {
        await caller.chat.sendMessage({
          conversationId: 1,
          message: "",
        });
        expect.fail("Should have thrown validation error");
      } catch (error: any) {
        expect(error.code).toBe("BAD_REQUEST");
      }
    });

    it("throws error if conversation not found", async () => {
      const { ctx } = createAuthContext();
      const caller = appRouter.createCaller(ctx);

      vi.mocked(db.getConversationById).mockResolvedValue(undefined);

      try {
        await caller.chat.sendMessage({
          conversationId: 999,
          message: "Hello",
        });
        expect.fail("Should have thrown error");
      } catch (error: any) {
        expect(error.message).toContain("Conversation not found");
      }
    });
  });
});
