import { z } from "zod";
import { ENV } from "./_core/env";
import { publicProcedure, protectedProcedure, router } from "./_core/trpc";

/** Make an authenticated request to the FastAPI backend. */
async function apiRequest(
  path: string,
  opts: {
    method?: string;
    body?: unknown;
    cookie?: string;
  } = {}
): Promise<unknown> {
  const res = await fetch(`${ENV.fastapiUrl}${path}`, {
    method: opts.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...(opts.cookie ? { Cookie: opts.cookie } : {}),
    },
    ...(opts.body !== undefined ? { body: JSON.stringify(opts.body) } : {}),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`FastAPI error ${res.status}: ${text}`);
  }
  return res.json();
}

export const appRouter = router({
  // ── Auth ──────────────────────────────────────────────────────────────
  auth: router({
    me: publicProcedure.query(({ ctx }) => ctx.user),

    logout: publicProcedure.mutation(({ ctx }) => {
      ctx.res.clearCookie("session_token", {
        httpOnly: true,
        secure: ENV.isProduction,
        sameSite: "lax",
        path: "/",
      });
      return { success: true } as const;
    }),
  }),

  // ── Waitlist ──────────────────────────────────────────────────────────
  waitlist: router({
    signup: publicProcedure
      .input(
        z.object({
          email: z.string().email(),
          name: z.string().optional(),
        })
      )
      .mutation(async ({ input }) => {
        const data = (await apiRequest("/api/waitlist", {
          method: "POST",
          body: input,
        })) as { success: boolean; isNew: boolean; message: string };
        return data;
      }),
  }),

  // ── Chat (conversations) ──────────────────────────────────────────────
  chat: router({
    createConversation: protectedProcedure
      .input(z.object({ title: z.string().optional() }))
      .mutation(async ({ input, ctx }) => {
        const data = (await apiRequest("/api/conversations", {
          method: "POST",
          body: { title: input.title },
          cookie: ctx.req.headers.cookie,
        })) as { id: number; title: string; created_at: string };
        return { success: true, conversationId: data.id };
      }),

    getConversations: protectedProcedure.query(async ({ ctx }) => {
      return apiRequest("/api/conversations", {
        cookie: ctx.req.headers.cookie,
      }) as Promise<
        Array<{
          id: number;
          title: string;
          created_at: string;
          updated_at: string;
        }>
      >;
    }),

    getMessages: protectedProcedure
      .input(z.object({ conversationId: z.number() }))
      .query(async ({ input, ctx }) => {
        return apiRequest(
          `/api/conversations/${input.conversationId}/messages`,
          {
            cookie: ctx.req.headers.cookie,
          }
        ) as Promise<
          Array<{
            id: number;
            role: string;
            content: string;
            created_at: string;
          }>
        >;
      }),

    sendMessage: protectedProcedure
      .input(
        z.object({
          conversationId: z.number(),
          message: z.string().min(1),
        })
      )
      .mutation(async ({ input, ctx }) => {
        const data = (await apiRequest(
          `/api/conversations/${input.conversationId}/chat`,
          {
            method: "POST",
            body: { message: input.message },
            cookie: ctx.req.headers.cookie,
          }
        )) as { response: string };
        return { success: true, assistantMessage: data.response };
      }),
  }),

  // ── User profile ──────────────────────────────────────────────────────
  profile: router({
    get: protectedProcedure.query(async ({ ctx }) => {
      return apiRequest("/api/profile", { cookie: ctx.req.headers.cookie });
    }),

    update: protectedProcedure
      .input(
        z.object({
          name: z.string().max(100).optional(),
          age: z.number().int().min(10).max(120).optional(),
          height: z.number().gt(50).lte(300).optional(),
          weight: z.number().gt(10).lte(500).optional(),
          gender: z.enum(["male", "female", "other"]).optional(),
          activity: z
            .enum(["sedentary", "moderate", "active", "athlete"])
            .optional(),
          goal: z
            .enum(["lose", "gain", "maintain", "recomposition"])
            .optional(),
          injuries: z.string().max(2000).optional(),
          onboarding_completed: z.boolean().optional(),
        })
      )
      .mutation(async ({ input, ctx }) => {
        return apiRequest("/api/profile", {
          method: "PUT",
          body: input,
          cookie: ctx.req.headers.cookie,
        });
      }),
  }),
});

export type AppRouter = typeof appRouter;
