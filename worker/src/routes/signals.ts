import { Hono } from "hono";
import { drizzle } from "drizzle-orm/d1";
import { Env } from "../types";
import { signalEvaluations, gateResults } from "../db/schema";

const app = new Hono<{ Bindings: Env }>();

app.post("/", async (c) => {
  const db = drizzle(c.env.DB);
  const body = await c.req.json<{
    signal: typeof signalEvaluations.$inferInsert;
    gates?: (typeof gateResults.$inferInsert)[];
  }>();

  try {
    const [inserted] = await db
      .insert(signalEvaluations)
      .values(body.signal)
      .returning();

    if (body.gates && body.gates.length > 0) {
      await db.insert(gateResults).values(body.gates);
    }

    return c.json({ ok: true, id: inserted.id, signalId: inserted.signalId }, 201);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return c.json({ ok: false, error: message }, 500);
  }
});

export default app;
