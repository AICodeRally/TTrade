import { Hono } from "hono";
import { drizzle } from "drizzle-orm/d1";
import { desc } from "drizzle-orm";
import { Env } from "../types";
import { weeklyReports } from "../db/schema";

const app = new Hono<{ Bindings: Env }>();

app.get("/", async (c) => {
  const db = drizzle(c.env.DB);
  const limitParam = c.req.query("limit");
  const limit = limitParam ? Math.min(parseInt(limitParam, 10), 52) : 12;

  const rows = await db
    .select()
    .from(weeklyReports)
    .orderBy(desc(weeklyReports.weekStart))
    .limit(limit);

  return c.json({ ok: true, reports: rows });
});

export default app;
