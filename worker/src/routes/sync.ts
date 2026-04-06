import { Hono } from "hono";
import { drizzle } from "drizzle-orm/d1";
import { Env } from "../types";
import {
  signalEvaluations,
  gateResults,
  executionEvents,
  tradeReviews,
  syncLog,
} from "../db/schema";

type SyncPayload = {
  signals?: (typeof signalEvaluations.$inferInsert)[];
  gates?: (typeof gateResults.$inferInsert)[];
  executions?: (typeof executionEvents.$inferInsert)[];
  reviews?: (typeof tradeReviews.$inferInsert)[];
};

const app = new Hono<{ Bindings: Env }>();

app.post("/", async (c) => {
  const db = drizzle(c.env.DB);
  const body = await c.req.json<SyncPayload>();
  const syncedAt = new Date().toISOString();
  const counts: Record<string, number> = {};

  try {
    if (body.signals && body.signals.length > 0) {
      await db
        .insert(signalEvaluations)
        .values(body.signals)
        .onConflictDoNothing();
      counts.signals = body.signals.length;
    }

    if (body.gates && body.gates.length > 0) {
      await db
        .insert(gateResults)
        .values(body.gates)
        .onConflictDoNothing();
      counts.gates = body.gates.length;
    }

    if (body.executions && body.executions.length > 0) {
      await db
        .insert(executionEvents)
        .values(body.executions)
        .onConflictDoNothing();
      counts.executions = body.executions.length;
    }

    if (body.reviews && body.reviews.length > 0) {
      await db
        .insert(tradeReviews)
        .values(body.reviews)
        .onConflictDoNothing();
      counts.reviews = body.reviews.length;
    }

    const totalRecords = Object.values(counts).reduce((a, b) => a + b, 0);

    await db.insert(syncLog).values({
      syncedAt,
      recordType: Object.keys(counts).join(","),
      recordCount: totalRecords,
      status: "success",
    });

    return c.json({ ok: true, syncedAt, counts });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);

    await db.insert(syncLog).values({
      syncedAt,
      recordType: "unknown",
      recordCount: 0,
      status: "error",
    });

    return c.json({ ok: false, error: message }, 500);
  }
});

export default app;
