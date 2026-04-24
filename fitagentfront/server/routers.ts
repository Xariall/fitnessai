import { z } from "zod";
import { ENV } from "./_core/env";
import { publicProcedure, protectedProcedure, router } from "./_core/trpc";

// ── Shared response types ─────────────────────────────────────────────────────
type PlanItem = {
  id: number;
  product_name: string;
  meal_type: string | null;
  weight_g: number;
  calories: number;
  protein: number;
  fat: number;
  carbs: number;
  order_index: number;
  consumed: boolean;
};
type NutritionPlan = {
  id: number;
  user_id: number;
  date: string;
  generated_by: string | null;
  notes: string | null;
  meals: Record<string, PlanItem[]>;
  created_at: string;
  updated_at: string;
};
type DailyNorm = {
  bmr: number;
  tdee: number;
  target_calories: number;
  protein_g: number;
  fat_g: number;
  carbs_g: number;
};

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

    deleteConversation: protectedProcedure
      .input(z.object({ conversationId: z.number() }))
      .mutation(async ({ input, ctx }) => {
        await apiRequest(`/api/conversations/${input.conversationId}`, {
          method: "DELETE",
          cookie: ctx.req.headers.cookie,
        });
        return { success: true };
      }),
  }),

  // ── User profile ──────────────────────────────────────────────────────
  profile: router({
    get: protectedProcedure.query(async ({ ctx }) => {
      return apiRequest("/api/profile", {
        cookie: ctx.req.headers.cookie,
      }) as Promise<{
        id: number;
        name: string | null;
        email: string | null;
        picture: string | null;
        age: number | null;
        height: number | null;
        weight: number | null;
        gender: string | null;
        activity: string | null;
        goal: string | null;
        injuries: string | null;
        conditions: string | null;
        food_allergies: string | null;
        meals_per_day: number | null;
        diet_type: string | null;
        food_budget: string | null;
        experience_level: string | null;
        training_location: string | null;
        training_days: number | null;
        session_duration: string | null;
        training_budget: string | null;
        onboarding_completed: boolean;
        nutrition_unlocked: boolean;
        workout_unlocked: boolean;
      }>;
    }),

    update: protectedProcedure
      .input(
        z.object({
          name: z.string().max(100).optional(),
          age: z.number().int().min(10).max(120).optional(),
          height: z.number().gt(50).lte(300).optional(),
          weight: z.number().gt(10).lte(500).optional(),
          gender: z
            .enum(["male", "female", "other", "prefer_not_to_say"])
            .optional(),
          activity: z
            .enum(["sedentary", "moderate", "active", "athlete"])
            .optional(),
          goal: z
            .enum([
              "lose",
              "gain",
              "maintain",
              "recomposition",
              "endurance",
              "healthy",
              "athletic",
            ])
            .optional(),
          injuries: z.string().max(2000).optional(),
          onboarding_completed: z.boolean().optional(),
          nutrition_unlocked: z.boolean().optional(),
          workout_unlocked: z.boolean().optional(),
        })
      )
      .mutation(async ({ input, ctx }) => {
        return apiRequest("/api/profile", {
          method: "PUT",
          body: input,
          cookie: ctx.req.headers.cookie,
        });
      }),

    submitOnboarding: protectedProcedure
      .input(
        z.object({
          // Block 1 — required
          name: z.string().min(1).max(100),
          gender: z.enum(["male", "female", "prefer_not_to_say"]),
          age: z.number().int().min(14).max(99),
          height: z.number().gt(50).lte(300),
          weight: z.number().gt(10).lte(500),
          goal: z.enum([
            "lose",
            "gain",
            "maintain",
            "recomposition",
            "endurance",
            "healthy",
            "athletic",
          ]),
          // Block 2 — required
          conditions: z.string().max(2000),
          injuries: z.string().max(2000),
          food_allergies: z.string().max(2000),
          // Block 3 — optional
          meals_per_day: z.number().int().min(1).max(10).optional(),
          diet_type: z.string().max(500).optional(),
          food_budget: z
            .enum(["under_30000", "30000_60000", "60000_120000", "over_120000"])
            .optional(),
          // Block 4 — optional
          experience_level: z
            .enum(["beginner", "some", "intermediate", "advanced"])
            .optional(),
          training_location: z.string().max(500).optional(),
          training_days: z.number().int().min(1).max(7).optional(),
          session_duration: z
            .enum(["20_30", "30_45", "45_60", "60_90", "over_90"])
            .optional(),
          training_budget: z
            .enum([
              "no_budget",
              "under_10000",
              "10000_25000",
              "25000_60000",
              "over_60000",
            ])
            .optional(),
        })
      )
      .mutation(async ({ input, ctx }) => {
        return apiRequest("/api/onboarding/complete", {
          method: "POST",
          body: input,
          cookie: ctx.req.headers.cookie,
        });
      }),
  }),

  // ── Nutrition ─────────────────────────────────────────────────────────
  nutrition: router({
    getPlan: protectedProcedure
      .input(z.object({ date: z.string() }))
      .query(async ({ input, ctx }) => {
        return apiRequest(
          `/api/nutrition/plan?date=${encodeURIComponent(input.date)}`,
          { cookie: ctx.req.headers.cookie }
        ) as Promise<{
          plan: NutritionPlan | null;
          daily_norm: DailyNorm | null;
        }>;
      }),

    generatePlan: protectedProcedure
      .input(
        z.object({
          date: z.string(),
          notes: z.string().optional(),
          meal_types: z
            .array(z.enum(["breakfast", "lunch", "dinner", "snack"]))
            .min(1)
            .optional(),
        })
      )
      .mutation(async ({ input, ctx }) => {
        return apiRequest("/api/nutrition/plan/generate", {
          method: "POST",
          body: {
            date: input.date,
            notes: input.notes ?? "",
            meal_types: input.meal_types ?? [
              "breakfast",
              "lunch",
              "dinner",
              "snack",
            ],
          },
          cookie: ctx.req.headers.cookie,
        }) as Promise<{ plan: NutritionPlan; daily_norm: DailyNorm | null }>;
      }),

    updateItem: protectedProcedure
      .input(z.object({ itemId: z.number(), weightG: z.number().positive() }))
      .mutation(async ({ input, ctx }) => {
        return apiRequest(`/api/nutrition/plan/item/${input.itemId}`, {
          method: "PATCH",
          body: { weight_g: input.weightG },
          cookie: ctx.req.headers.cookie,
        }) as Promise<PlanItem>;
      }),

    addItem: protectedProcedure
      .input(
        z.object({
          planId: z.number(),
          mealType: z.string().optional(),
          productName: z.string().min(1),
          weightG: z.number().positive(),
        })
      )
      .mutation(async ({ input, ctx }) => {
        return apiRequest("/api/nutrition/plan/item", {
          method: "POST",
          body: {
            plan_id: input.planId,
            meal_type: input.mealType ?? null,
            product_name: input.productName,
            weight_g: input.weightG,
          },
          cookie: ctx.req.headers.cookie,
        }) as Promise<PlanItem>;
      }),

    deleteItem: protectedProcedure
      .input(z.object({ itemId: z.number() }))
      .mutation(async ({ input, ctx }) => {
        const res = await fetch(
          `${ENV.fastapiUrl}/api/nutrition/plan/item/${input.itemId}`,
          {
            method: "DELETE",
            headers: {
              "Content-Type": "application/json",
              ...(ctx.req.headers.cookie
                ? { Cookie: ctx.req.headers.cookie }
                : {}),
            },
          }
        );
        if (!res.ok) {
          const text = await res.text().catch(() => res.statusText);
          throw new Error(`FastAPI error ${res.status}: ${text}`);
        }
        return { success: true } as const;
      }),

    toggleConsumed: protectedProcedure
      .input(z.object({ itemId: z.number(), consumed: z.boolean() }))
      .mutation(async ({ input, ctx }) => {
        return apiRequest(`/api/nutrition/plan/item/${input.itemId}/consumed`, {
          method: "PATCH",
          body: { consumed: input.consumed },
          cookie: ctx.req.headers.cookie,
        }) as Promise<PlanItem>;
      }),

    getDiary: protectedProcedure
      .input(z.object({ date: z.string() }))
      .query(async ({ input, ctx }) => {
        return apiRequest(
          `/api/nutrition/diary?date=${encodeURIComponent(input.date)}`,
          { cookie: ctx.req.headers.cookie }
        ) as Promise<{
          entries: Array<{
            id: number;
            product_name: string;
            weight_g: number;
            calories: number;
            protein: number;
            fat: number;
            carbs: number;
            logged_at: string;
          }>;
          summary: {
            calories: number;
            protein: number;
            fat: number;
            carbs: number;
            meals: number;
          };
        }>;
      }),
  }),

  // ── Workout programs ──────────────────────────────────────────────────────
  workout: router({
    getActive: protectedProcedure.query(async ({ ctx }) => {
      return apiRequest("/api/workout-programs/active", {
        cookie: ctx.req.headers.cookie,
      }) as Promise<WorkoutProgram | null>;
    }),

    getAll: protectedProcedure.query(async ({ ctx }) => {
      return apiRequest("/api/workout-programs", {
        cookie: ctx.req.headers.cookie,
      }) as Promise<WorkoutProgram[]>;
    }),

    generate: protectedProcedure
      .input(z.object({ days_per_week: z.number().min(1).max(7).default(3) }))
      .mutation(async ({ input, ctx }) => {
        return apiRequest("/api/workout-programs/generate", {
          method: "POST",
          body: { days_per_week: input.days_per_week },
          cookie: ctx.req.headers.cookie,
        }) as Promise<WorkoutProgram>;
      }),

    delete: protectedProcedure
      .input(z.object({ programId: z.number() }))
      .mutation(async ({ input, ctx }) => {
        return apiRequest(`/api/workout-programs/${input.programId}`, {
          method: "DELETE",
          cookie: ctx.req.headers.cookie,
        }) as Promise<{ success: boolean }>;
      }),
  }),

  // ── Progress ──────────────────────────────────────────────────────────────
  progress: router({
    getSummary: protectedProcedure.query(async ({ ctx }) => {
      return apiRequest("/api/progress/summary", {
        cookie: ctx.req.headers.cookie,
      }) as Promise<{
        current_weight: number | null;
        weight_change_90d: number | null;
        total_workouts: number;
        weight_history: Array<{ weight: number; logged_at: string }>;
        recent_workouts: Array<{
          id: number;
          exercise: string;
          sets: number;
          reps: number;
          weight_kg: number | null;
          logged_at: string;
        }>;
        profile: {
          goal: string | null;
          height: number | null;
          activity: string | null;
        };
      }>;
    }),

    logWeight: protectedProcedure
      .input(z.object({ weight: z.number().positive() }))
      .mutation(async ({ input, ctx }) => {
        return apiRequest("/api/progress/weight", {
          method: "POST",
          body: { weight: input.weight },
          cookie: ctx.req.headers.cookie,
        }) as Promise<{ success: boolean; weight: number }>;
      }),
  }),
});

// ── Workout types ─────────────────────────────────────────────────────────────
type WorkoutExercise = {
  name: string;
  description: string;
  sets: number;
  reps: string;
  weight: string;
  rest: string;
};

type WorkoutDayPlan = WorkoutExercise[];

type WorkoutProgram = {
  id: number;
  name: string;
  goal: string | null;
  level: string | null;
  level_label?: string;
  days_per_week: number | null;
  program_json: string;
  program?: Record<string, WorkoutDayPlan>;
  created_at: string;
};

export type AppRouter = typeof appRouter;
