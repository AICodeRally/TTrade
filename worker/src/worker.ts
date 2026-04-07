import { Hono } from "hono";
import { cors } from "hono/cors";
import { Env } from "./types";
import { authMiddleware } from "./middleware/auth";
import signalsApp from "./routes/signals";
import executionsApp from "./routes/executions";
import reviewsApp from "./routes/reviews";
import journalApp from "./routes/journal";
import syncApp from "./routes/sync";
import reportsApp from "./routes/reports";
import dashboardApp from "./routes/dashboard";
import marketApp from "./routes/market";
import aiApp from "./routes/ai";

const app = new Hono<{ Bindings: Env }>();

app.use("*", cors());

app.get("/", (c) => c.json({ name: "ttrade-worker", version: "1.1.0", status: "ok" }));

app.use("/signals/*", authMiddleware);
app.use("/executions/*", authMiddleware);
app.use("/reviews/*", authMiddleware);
app.use("/sync/*", authMiddleware);

// Dashboard/market routes require a dashboard token
app.use("/dashboard/*", async (c, next) => {
  const token = c.req.query("token") || c.req.header("Authorization")?.replace("Bearer ", "");
  if (!token || token !== c.env.DASHBOARD_TOKEN) return c.json({ error: "Unauthorized" }, 401);
  await next();
});
app.use("/market/*", async (c, next) => {
  const token = c.req.query("token") || c.req.header("Authorization")?.replace("Bearer ", "");
  if (!token || token !== c.env.DASHBOARD_TOKEN) return c.json({ error: "Unauthorized" }, 401);
  await next();
});
app.use("/journal/*", async (c, next) => {
  const token = c.req.query("token") || c.req.header("Authorization")?.replace("Bearer ", "");
  if (!token || token !== c.env.DASHBOARD_TOKEN) return c.json({ error: "Unauthorized" }, 401);
  await next();
});
app.use("/ai/*", async (c, next) => {
  const token = c.req.query("token") || c.req.header("Authorization")?.replace("Bearer ", "");
  if (!token || token !== c.env.DASHBOARD_TOKEN) return c.json({ error: "Unauthorized" }, 401);
  await next();
});

app.route("/signals", signalsApp);
app.route("/executions", executionsApp);
app.route("/reviews", reviewsApp);
app.route("/journal", journalApp);
app.route("/dashboard", dashboardApp);
app.route("/sync", syncApp);
app.route("/reports", reportsApp);
app.route("/market", marketApp);
app.route("/ai", aiApp);

export default app;
