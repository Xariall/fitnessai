export { COOKIE_NAME, ONE_YEAR_MS } from "@shared/const";

/**
 * Redirects the browser directly to the FastAPI backend on Railway.
 */
export const getLoginUrl = () =>
  "https://fitnessai-production-1346.up.railway.app/api/auth/google";
