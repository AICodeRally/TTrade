import { Hono } from "hono";
import { drizzle } from "drizzle-orm/d1";
import { desc } from "drizzle-orm";
import { Env } from "../types";
import { signalEvaluations, executionEvents, tradeReviews } from "../db/schema";

const app = new Hono<{ Bindings: Env }>();

app.get("/", async (c) => {
  const db = drizzle(c.env.DB);
  const limitParam = c.req.query("limit");
  const limit = limitParam ? Math.min(parseInt(limitParam, 10), 100) : 20;

  const [signals, executions, reviews] = await Promise.all([
    db
      .select()
      .from(signalEvaluations)
      .orderBy(desc(signalEvaluations.createdAt))
      .limit(limit),
    db
      .select()
      .from(executionEvents)
      .orderBy(desc(executionEvents.createdAt))
      .limit(limit),
    db
      .select()
      .from(tradeReviews)
      .orderBy(desc(tradeReviews.createdAt))
      .limit(limit),
  ]);

  return c.json({ ok: true, signals, executions, reviews });
});

export default app;
