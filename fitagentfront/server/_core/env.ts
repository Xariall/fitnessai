/** On Vercel, VERCEL_URL is the auto-generated deployment hostname (no scheme). */
const vercelOrigin = process.env.VERCEL_URL
  ? `https://${process.env.VERCEL_URL}`
  : undefined;

export const ENV = {
  /**
   * Internal URL for server-to-server calls to FastAPI.
   * Docker: http://api:8000 | Vercel/production: your deployed FastAPI URL.
   */
  fastapiUrl: process.env.FASTAPI_URL ?? "http://localhost:8000",

  /**
   * PUBLIC base URL of FastAPI — used for browser-visible OAuth redirects.
   * Must be resolvable by the user's browser.
   */
  fastapiBaseUrl:
    process.env.FASTAPI_BASE_URL ??
    process.env.FASTAPI_URL ??
    "http://localhost:8000",

  /** Shared secret for verifying JWTs signed by FastAPI */
  jwtSecret: process.env.JWT_SECRET ?? "",

  /**
   * Public URL of this frontend.
   * Falls back to the auto-generated Vercel deployment URL when available.
   */
  frontendUrl:
    process.env.FRONTEND_URL ?? vercelOrigin ?? "http://localhost:3000",

  isProduction: process.env.NODE_ENV === "production",
};
