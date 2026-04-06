import { Context, Next } from "hono";
import { Env } from "../types";

export async function authMiddleware(c: Context<{ Bindings: Env }>, next: Next) {
  const apiKey = c.req.header("X-API-Key");
  if (!apiKey || apiKey !== c.env.SYNC_API_KEY) {
    return c.json({ error: "Unauthorized" }, 401);
  }
  await next();
}
