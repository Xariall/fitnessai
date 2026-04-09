import type { CreateExpressContextOptions } from "@trpc/server/adapters/express";
import { parse as parseCookies } from "cookie";
import { jwtVerify } from "jose";
import { ENV } from "./env";

export type SessionUser = {
  id: number;
  email: string | null;
  name: string | null;
};

export type TrpcContext = {
  req: CreateExpressContextOptions["req"];
  res: CreateExpressContextOptions["res"];
  user: SessionUser | null;
};

async function getUserFromCookie(cookieHeader: string | undefined): Promise<SessionUser | null> {
  if (!cookieHeader) return null;
  const cookies = parseCookies(cookieHeader);
  const token = cookies["session_token"];
  if (!token) return null;

  try {
    const secret = new TextEncoder().encode(ENV.jwtSecret);
    const { payload } = await jwtVerify(token, secret, { algorithms: ["HS256"] });
    const id = Number(payload.sub);
    if (!id || isNaN(id)) return null;
    return {
      id,
      email: (payload.email as string) ?? null,
      name: (payload.name as string) ?? null,
    };
  } catch {
    return null;
  }
}

export async function createContext(
  opts: CreateExpressContextOptions
): Promise<TrpcContext> {
  const user = await getUserFromCookie(opts.req.headers.cookie);
  return { req: opts.req, res: opts.res, user };
}
