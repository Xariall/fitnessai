import "dotenv/config";
import express from "express";
import fs from "fs";
import { createServer } from "http";
import net from "net";
import path from "path";
import { Readable } from "node:stream";
import { fileURLToPath } from "url";
import { createExpressMiddleware } from "@trpc/server/adapters/express";
import { appRouter } from "../routers";
import { createContext } from "./context";
import { ENV } from "./env";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function isPortAvailable(port: number): Promise<boolean> {
  return new Promise(resolve => {
    const server = net.createServer();
    server.listen(port, () => {
      server.close(() => resolve(true));
    });
    server.on("error", () => resolve(false));
  });
}

async function findAvailablePort(startPort: number = 3000): Promise<number> {
  for (let port = startPort; port < startPort + 20; port++) {
    if (await isPortAvailable(port)) return port;
  }
  throw new Error(`No available port found starting from ${startPort}`);
}

async function startServer() {
  const app = express();
  const server = createServer(app);

  app.use(express.json({ limit: "10mb" }));
  app.use(express.urlencoded({ limit: "10mb", extended: true }));

  /**
   * OAuth finish route — called by FastAPI after completing Google OAuth.
   * FastAPI redirects here with ?token=<JWT>; we set the httpOnly cookie
   * and redirect the user to the home page.
   */
  app.get("/api/oauth/finish", (req, res) => {
    const token = req.query.token as string | undefined;
    if (!token) {
      return res.redirect("/?error=missing_token");
    }
    res.cookie("session_token", token, {
      httpOnly: true,
      secure: ENV.isProduction,
      sameSite: "lax",
      path: "/",
      maxAge: 30 * 24 * 60 * 60 * 1000, // 30 days
    });
    return res.redirect("/");
  });

  /** Legacy OAuth start route — kept for backwards compatibility.
   *  The frontend now links directly to the FastAPI /api/auth/google endpoint. */
  app.get("/api/oauth/start", (_req, res) => {
    res.redirect(`${ENV.fastapiBaseUrl}/api/auth/google`);
  });

  // ── Chat streaming proxy ──────────────────────────────────────────────────
  // Pipes FastAPI SSE stream to the browser, forwarding the session cookie.
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

      readable = Readable.fromWeb(
        upstream.body as Parameters<typeof Readable.fromWeb>[0]
      );
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

  // tRPC
  app.use(
    "/api/trpc",
    createExpressMiddleware({ router: appRouter, createContext })
  );

  if (process.env.NODE_ENV === "development") {
    // Dynamic import keeps vite out of the production bundle entirely
    const { setupVite } = await import("./vite.js");
    await setupVite(app, server);
  } else {
    // Serve the Vite-built client from dist/public (relative to dist/index.js)
    const distPath = path.resolve(__dirname, "public");
    if (!fs.existsSync(distPath)) {
      console.error(
        `Build directory not found: ${distPath}. Run pnpm build first.`
      );
    }
    app.use(express.static(distPath));
    app.use("*", (_req, res) => {
      res.sendFile(path.resolve(distPath, "index.html"));
    });
  }

  const preferredPort = parseInt(process.env.PORT ?? "3000");
  const port = await findAvailablePort(preferredPort);

  if (port !== preferredPort) {
    console.log(`Port ${preferredPort} is busy, using ${port} instead`);
  }

  server.listen(port, () => {
    console.log(`Frontend server running on http://localhost:${port}/`);
  });
}

startServer().catch(console.error);
