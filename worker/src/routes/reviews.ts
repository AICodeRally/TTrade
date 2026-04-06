import { Hono } from "hono";
import { drizzle } from "drizzle-orm/d1";
import { desc } from "drizzle-orm";
import { Env } from "../types";
import { tradeReviews } from "../db/schema";

const app = new Hono<{ Bindings: Env }>();

app.post("/", async (c) => {
  const db = drizzle(c.env.DB);
  const body = await c.req.json<typeof tradeReviews.$inferInsert>();

  try {
    const [inserted] = await db
      .insert(tradeReviews)
      .values(body)
      .returning();

    return c.json({ ok: true, id: inserted.id, reviewId: inserted.reviewId }, 201);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return c.json({ ok: false, error: message }, 500);
  }
});

app.get("/", async (c) => {
  const db = drizzle(c.env.DB);
  const limitParam = c.req.query("limit");
  const limit = limitParam ? Math.min(parseInt(limitParam, 10), 200) : 50;

  const rows = await db
    .select()
    .from(tradeReviews)
    .orderBy(desc(tradeReviews.createdAt))
    .limit(limit);

  return c.json({ ok: true, reviews: rows });
});

export default app;
