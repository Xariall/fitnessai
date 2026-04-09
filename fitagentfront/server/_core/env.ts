export const ENV = {
  /**
   * Internal URL for server-to-server calls to FastAPI.
   * In Docker this is http://api:8000 (Docker network name).
   */
  fastapiUrl: process.env.FASTAPI_URL ?? "http://localhost:8000",
  /**
   * PUBLIC base URL of FastAPI — used for browser-visible redirects (OAuth).
   * Must be resolvable by the user's browser, e.g. http://localhost:8000.
   * Falls back to fastapiUrl when not set (fine for local dev without Docker).
   */
  fastapiBaseUrl:
    process.env.FASTAPI_BASE_URL ??
    process.env.FASTAPI_URL ??
    "http://localhost:8000",
  /** Shared secret for verifying JWTs signed by FastAPI */
  jwtSecret: process.env.JWT_SECRET ?? "",
  /** URL of this frontend server (used in redirect links) */
  frontendUrl: process.env.FRONTEND_URL ?? "http://localhost:3000",
  isProduction: process.env.NODE_ENV === "production",
};
