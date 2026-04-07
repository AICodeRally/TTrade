import { Hono } from "hono";
import { drizzle } from "drizzle-orm/d1";
import { desc, eq } from "drizzle-orm";
import { Env } from "../types";
import { positions, signalEvaluations, gateResults, tradeReviews } from "../db/schema";

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

  // Enrich signals with gate results
  const signalIds = recentSignals.map(s => s.signalId);
  let allGates: (typeof gateResults.$inferSelect)[] = [];
  if (signalIds.length > 0) {
    // Fetch gates for all recent signals
    for (const sid of signalIds.slice(0, 5)) {
      const gates = await db
        .select()
        .from(gateResults)
        .where(eq(gateResults.signalId, sid));
      allGates.push(...gates);
    }
  }

  // Group gates by signal ID
  const gatesBySignal: Record<string, typeof allGates> = {};
  for (const g of allGates) {
    if (!gatesBySignal[g.signalId]) gatesBySignal[g.signalId] = [];
    gatesBySignal[g.signalId].push(g);
  }

  // Attach gate results to signals
  const enrichedSignals = recentSignals.map(s => ({
    ...s,
    gateResultsJson: gatesBySignal[s.signalId]
      ? JSON.stringify(gatesBySignal[s.signalId].map(g => ({
          gate_name: g.gateName,
          passed: g.passed,
          measured_value: g.measuredValue,
          threshold: g.threshold,
        })))
      : null,
  }));

  return c.json({
    ok: true,
    openPositions,
    recentSignals: enrichedSignals,
    recentReviews,
  });
});

export default app;
