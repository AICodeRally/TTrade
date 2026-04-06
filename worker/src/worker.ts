import { Hono } from "hono";
import { Env } from "./types";
import { authMiddleware } from "./middleware/auth";
import signalsApp from "./routes/signals";
import executionsApp from "./routes/executions";
import reviewsApp from "./routes/reviews";
import journalApp from "./routes/journal";
import syncApp from "./routes/sync";
import reportsApp from "./routes/reports";
import dashboardApp from "./routes/dashboard";

const app = new Hono<{ Bindings: Env }>();

app.get("/", (c) => c.json({ name: "ttrade-worker", version: "1.1.0", status: "ok" }));

app.use("/signals/*", authMiddleware);
app.use("/executions/*", authMiddleware);
app.use("/reviews/*", authMiddleware);
app.use("/sync/*", authMiddleware);

app.route("/signals", signalsApp);
app.route("/executions", executionsApp);
app.route("/reviews", reviewsApp);
app.route("/journal", journalApp);
app.route("/dashboard", dashboardApp);
app.route("/sync", syncApp);
app.route("/reports", reportsApp);

export default app;
