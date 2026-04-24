/**
 * Vercel Serverless Function entry-point.
 *
 * Vercel automatically detects files inside api/ and exposes them as
 * serverless functions. vercel.json rewrites all /api/* traffic here,
 * so Express handles individual routes as usual.
 *
 * NOTE: Static files (dist/public) are served by Vercel's CDN — this
 * function only handles API + OAuth routes.
 */
import express from "express";
import { Readable } from "node:stream";
import { createExpressMiddleware } from "@trpc/server/adapters/express";
import { appRouter } from "../routers";
import { createContext } from "./context";
import { ENV } from "./env";

const app = express();

app.use(express.json({ limit: "10mb" }));
app.use(express.urlencoded({ limit: "10mb", extended: true }));

/**
 * OAuth finish — FastAPI redirects here after Google OAuth.
 * Sets an httpOnly session cookie and redirects the user to home.
 */
app.get("/api/oauth/finish", (req, res) => {
  const token = req.query.token as string | undefined;
  if (!token) {
    return res.redirect("/?error=missing_token");
  }
  res.cookie("session_token", token, {
    httpOnly: true,
    secure: true,          // always true on Vercel (HTTPS)
    sameSite: "lax",
    path: "/",
    maxAge: 30 * 24 * 60 * 60 * 1000, // 30 days
  });
  return res.redirect("/");
});

/** Initiates Google OAuth — browser follows to the public FastAPI URL. */
app.get("/api/oauth/start", (_req, res) => {
  res.redirect(`${ENV.fastapiBaseUrl}/api/auth/google`);
});

// Chat streaming proxy — pipes FastAPI SSE stream to the browser
app.post("/api/chat-stream/:convId", async (req, res) => {
  const cookie = req.headers.cookie;
  if (!cookie) {
    res.status(401).json({ error: "Unauthorized" });
    return;
  }

  const { message } = req.body as { message?: string };
  if (!message) {
    res.status(400).json({ error: "message required" });
    return;
  }

  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.setHeader("X-Accel-Buffering", "no");
  res.flushHeaders();

  let readable: Readable | null = null;
  try {
    const upstream = await fetch(
      `${ENV.fastapiUrl}/api/conversations/${req.params.convId}/chat/stream`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", Cookie: cookie },
        body: JSON.stringify({ message }),
      }
    );

    if (!upstream.ok || !upstream.body) {
      res.write(
        `data: ${JSON.stringify({ type: "error", text: "Upstream error" })}\n\n`
      );
      res.end();
      return;
    }

    readable = Readable.fromWeb(upstream.body as Parameters<typeof Readable.fromWeb>[0]);
    readable.pipe(res);
    req.on("close", () => readable?.destroy());
  } catch {
    if (!res.writableEnded) {
      res.write(
        `data: ${JSON.stringify({ type: "error", text: "Connection error" })}\n\n`
      );
      res.end();
    }
  }
});

// tRPC — thin proxy to FastAPI
app.use(
  "/api/trpc",
  createExpressMiddleware({ router: appRouter, createContext })
);

export default app;
