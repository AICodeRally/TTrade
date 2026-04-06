import { Hono } from "hono";
import { drizzle } from "drizzle-orm/d1";
import { Env } from "../types";
import { executionEvents } from "../db/schema";

const app = new Hono<{ Bindings: Env }>();

app.post("/", async (c) => {
  const db = drizzle(c.env.DB);
  const body = await c.req.json<typeof executionEvents.$inferInsert>();

  try {
    const [inserted] = await db
      .insert(executionEvents)
      .values(body)
      .returning();

    return c.json({ ok: true, id: inserted.id, executionId: inserted.executionId }, 201);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return c.json({ ok: false, error: message }, 500);
  }
});

export default app;
