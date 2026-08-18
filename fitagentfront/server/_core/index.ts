import "dotenv/config";
import express from "express";
import fs from "fs";
import { createServer } from "http";
import net from "net";
import path from "path";
import { fileURLToPath } from "url";

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
