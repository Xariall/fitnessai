export { COOKIE_NAME, ONE_YEAR_MS } from "@shared/const";

/**
 * Redirects the browser to the Express OAuth start route, which forwards
 * to FastAPI /api/auth/google → Google → FastAPI callback → Express finish → home.
 */
export const getLoginUrl = () => "/api/oauth/start";
