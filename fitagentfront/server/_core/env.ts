const isProd = process.env.NODE_ENV === "production";

/** On Vercel, VERCEL_URL is the auto-generated deployment hostname (no scheme). */
const vercelOrigin = process.env.VERCEL_URL
  ? `https://${process.env.VERCEL_URL}`
  : undefined;

function requireEnv(name: string, fallback?: string): string {
  const value = process.env[name] ?? fallback;
  if (!value && isProd) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value ?? "";
}

export const ENV = {
  /**
   * Internal URL for server-to-server calls to FastAPI.
   * Vercel → Railway: https://fitnessai-production-1346.up.railway.app
   * Docker: http://api:8000
   */
  fastapiUrl: requireEnv("FASTAPI_URL", "http://localhost:8000"),

  /**
   * PUBLIC base URL of FastAPI — used for browser-visible OAuth redirects.
   * Must be resolvable by the user's browser.
   */
  fastapiBaseUrl: requireEnv(
    "FASTAPI_BASE_URL",
    process.env.FASTAPI_URL ?? "http://localhost:8000"
  ),

  /** Shared secret for verifying JWTs signed by FastAPI */
  jwtSecret: requireEnv("JWT_SECRET"),

  /**
   * Public URL of this frontend.
   * Falls back to the auto-generated Vercel deployment URL when available.
   */
  frontendUrl: requireEnv(
    "FRONTEND_URL",
    vercelOrigin ?? "http://localhost:3000"
  ),

  isProduction: isProd,
};
