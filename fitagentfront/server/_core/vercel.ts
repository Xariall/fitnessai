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

// tRPC — thin proxy to FastAPI
app.use(
  "/api/trpc",
  createExpressMiddleware({ router: appRouter, createContext })
);

export default app;
