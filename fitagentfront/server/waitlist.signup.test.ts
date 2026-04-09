import { describe, expect, it, beforeEach, vi } from "vitest";
import { appRouter } from "./routers";
import type { TrpcContext } from "./_core/context";

// Mock database functions
vi.mock("./db", () => ({
  addToWaitlist: vi.fn(),
  getWaitlistByEmail: vi.fn(),
}));

import * as db from "./db";

function createPublicContext(): TrpcContext {
  return {
    user: null,
    req: {
      protocol: "https",
      headers: {},
    } as TrpcContext["req"],
    res: {
      clearCookie: vi.fn(),
    } as unknown as TrpcContext["res"],
  };
}

describe("waitlist.signup", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("successfully adds new email to waitlist", async () => {
    const ctx = createPublicContext();
    const caller = appRouter.createCaller(ctx);

    vi.mocked(db.getWaitlistByEmail).mockResolvedValue(undefined);
    vi.mocked(db.addToWaitlist).mockResolvedValue(undefined);

    const result = await caller.waitlist.signup({
      email: "test@example.com",
      name: "Test User",
    });

    expect(result).toEqual({
      success: true,
      message: "Successfully added to waitlist",
      isNew: true,
    });
    expect(db.getWaitlistByEmail).toHaveBeenCalledWith("test@example.com");
    expect(db.addToWaitlist).toHaveBeenCalledWith("test@example.com", "Test User");
  });

  it("returns existing message if email already on waitlist", async () => {
    const ctx = createPublicContext();
    const caller = appRouter.createCaller(ctx);

    const existingEntry = {
      id: 1,
      email: "existing@example.com",
      name: "Existing User",
      status: "pending" as const,
      createdAt: new Date(),
      updatedAt: new Date(),
    };

    vi.mocked(db.getWaitlistByEmail).mockResolvedValue(existingEntry);

    const result = await caller.waitlist.signup({
      email: "existing@example.com",
      name: "Existing User",
    });

    expect(result).toEqual({
      success: true,
      message: "You are already on the waitlist",
      isNew: false,
    });
    expect(db.addToWaitlist).not.toHaveBeenCalled();
  });

  it("rejects invalid email format", async () => {
    const ctx = createPublicContext();
    const caller = appRouter.createCaller(ctx);

    try {
      await caller.waitlist.signup({
        email: "invalid-email",
        name: "Test User",
      });
      expect.fail("Should have thrown validation error");
    } catch (error: any) {
      expect(error.code).toBe("BAD_REQUEST");
    }
  });

  it("works with optional name field", async () => {
    const ctx = createPublicContext();
    const caller = appRouter.createCaller(ctx);

    vi.mocked(db.getWaitlistByEmail).mockResolvedValue(undefined);
    vi.mocked(db.addToWaitlist).mockResolvedValue(undefined);

    const result = await caller.waitlist.signup({
      email: "noname@example.com",
    });

    expect(result.success).toBe(true);
    expect(db.addToWaitlist).toHaveBeenCalledWith("noname@example.com", undefined);
  });
});
