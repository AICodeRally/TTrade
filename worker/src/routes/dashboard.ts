import { Hono } from "hono";
import { drizzle } from "drizzle-orm/d1";
import { desc, eq } from "drizzle-orm";
import { Env } from "../types";
import { positions, signalEvaluations, tradeReviews } from "../db/schema";

const app = new Hono<{ Bindings: Env }>();

app.get("/", async (c) => {
  const db = drizzle(c.env.DB);

  const [openPositions, recentSignals, recentReviews] = await Promise.all([
    db
      .select()
      .from(positions)
      .where(eq(positions.status, "open"))
      .orderBy(desc(positions.openedAt))
      .limit(50),
    db
      .select()
      .from(signalEvaluations)
      .orderBy(desc(signalEvaluations.timestamp))
      .limit(20),
    db
      .select()
      .from(tradeReviews)
      .orderBy(desc(tradeReviews.createdAt))
      .limit(10),
  ]);

  return c.json({
    ok: true,
    openPositions,
    recentSignals,
    recentReviews,
  });
});

export default app;
