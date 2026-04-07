import { Hono } from "hono";
import { Env } from "../types";

const app = new Hono<{ Bindings: Env }>();

// ── CF AI Gateway config ────────────────────────────────────
const CF_ACCOUNT_ID = "6ceba245c301bc15f3bea5653778b760";
const CF_GATEWAY_NAME = "aicr";
const BYOK_ALIAS = "anthro-01";
const MODEL = "claude-haiku-4-5-20251001";

function gatewayUrl(): string {
  return `https://gateway.ai.cloudflare.com/v1/${CF_ACCOUNT_ID}/${CF_GATEWAY_NAME}/anthropic/v1/messages`;
}

function gatewayHeaders(aigToken: string): Record<string, string> {
  return {
    "content-type": "application/json",
    "cf-aig-authorization": `Bearer ${aigToken}`,
    "cf-aig-byok-alias": BYOK_ALIAS,
    "anthropic-version": "2023-06-01",
  };
}

async function callClaude(
  aigToken: string,
  system: string,
  userPrompt: string,
  maxTokens = 512,
): Promise<string> {
  const resp = await fetch(gatewayUrl(), {
    method: "POST",
    headers: gatewayHeaders(aigToken),
    body: JSON.stringify({
      model: MODEL,
      max_tokens: maxTokens,
      system,
      messages: [{ role: "user", content: userPrompt }],
    }),
  });

  if (!resp.ok) {
    const errText = await resp.text();
    throw new Error(`Gateway ${resp.status}: ${errText.slice(0, 200)}`);
  }

  const result = (await resp.json()) as {
    content: Array<{ type: string; text: string }>;
  };
  return result.content?.[0]?.text || "";
}

interface AnalyzeRequest {
  ticker: string;
  direction: "bullish" | "bearish";
  signal_score: number;
  component_scores: Record<string, number>;
  market_state: string;
  gate_results: Array<{
    gate_name: string;
    passed: boolean;
    measured_value: string;
    threshold: string;
  }>;
  recent_prices: Array<{ date: string; open: number; high: number; low: number; close: number; volume: number }>;
  news_headlines: string[];
}

interface AnalyzeResponse {
  conviction: number; // 0-100
  reasoning: string;
  risk_factors: string[];
  trade_quality: "A" | "B" | "C" | "PASS";
  summary: string;
}

const SYSTEM_PROMPT = `You are a disciplined options trading analyst for a small account ($1,000). You evaluate vertical spread setups on stocks and ETFs.

Your role:
- Analyze the technical setup, news context, and gate results
- Provide a conviction score (0-100) and trade quality grade
- Identify specific risk factors
- Be conservative — this is real money in a small account

Scoring guide:
- 80-100: Strong setup, clear trend, confirming volume, no red flags
- 60-79: Decent setup with minor concerns
- 40-59: Marginal, would need perfect execution
- 0-39: Pass — too many risk factors

Trade quality grades:
- A: Take the trade confidently
- B: Take it but size down or tighten stops
- C: Only if nothing better available
- PASS: Skip this one

Always respond with valid JSON matching this schema:
{
  "conviction": <number 0-100>,
  "reasoning": "<2-3 sentences explaining your analysis>",
  "risk_factors": ["<specific risk 1>", "<specific risk 2>"],
  "trade_quality": "<A|B|C|PASS>",
  "summary": "<one line: TICKER DIRECTION — key insight>"
}`;

app.post("/analyze", async (c) => {
  const aigToken = c.env.CF_AIG_TOKEN;
  if (!aigToken) {
    return c.json({ ok: false, error: "CF_AIG_TOKEN not configured" }, 500);
  }

  const body = await c.req.json<AnalyzeRequest>();

  const priceContext = body.recent_prices
    .slice(-10)
    .map((p) => `${p.date}: O=${p.open.toFixed(2)} H=${p.high.toFixed(2)} L=${p.low.toFixed(2)} C=${p.close.toFixed(2)} V=${(p.volume / 1e6).toFixed(1)}M`)
    .join("\n");

  const gateContext = body.gate_results
    .map((g) => `${g.gate_name}: ${g.passed ? "PASS" : "FAIL"} (${g.measured_value} vs ${g.threshold})`)
    .join("\n");

  const scoreContext = Object.entries(body.component_scores)
    .map(([k, v]) => `${k}: ${typeof v === "number" ? v.toFixed(1) : v}`)
    .join(", ");

  const newsContext =
    body.news_headlines.length > 0
      ? `Recent headlines:\n${body.news_headlines.slice(0, 5).map((h) => `- ${h}`).join("\n")}`
      : "No recent news available.";

  const userPrompt = `Analyze this ${body.direction} vertical spread setup on ${body.ticker}:

Market State: ${body.market_state}
Signal Score: ${body.signal_score.toFixed(1)}/100
Score Components: ${scoreContext}

Gate Results (all passed):
${gateContext}

Recent Price Action (last 10 bars):
${priceContext}

${newsContext}

Provide your conviction analysis as JSON.`;

  try {
    const text = await callClaude(aigToken, SYSTEM_PROMPT, userPrompt);
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      return c.json({ ok: false, error: "Failed to parse AI response", raw: text }, 500);
    }
    const analysis = JSON.parse(jsonMatch[0]) as AnalyzeResponse;
    return c.json({ ok: true, analysis });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return c.json({ ok: false, error: msg }, 502);
  }
});

interface ReviewTradeRequest {
  ticker: string;
  direction: string;
  signal_score: number;
  entry_debit: number;
  exit_credit: number;
  pnl_pct: number;
  pnl_dollars: number;
  hold_duration_hours: number;
  exit_reason: string;
  setup_grade: string;
  execution_grade: string;
  outcome_grade: string;
  failure_tags: string[];
  market_state_at_entry: string;
  market_state_at_exit: string;
}

const REVIEW_SYSTEM_PROMPT = `You are a trading coach reviewing completed vertical spread trades for a small account ($1,000). Your job is to provide honest, actionable feedback.

For each trade, provide:
1. What went right (be specific about the setup/execution)
2. What went wrong (be specific about mistakes)
3. Key lesson (one concrete, actionable takeaway)
4. Grade adjustment (if you disagree with the mechanical grades, explain why)
5. Pattern detection (is this a recurring mistake or strength?)

Always respond with valid JSON:
{
  "what_went_right": "<1-2 sentences>",
  "what_went_wrong": "<1-2 sentences, or 'Nothing significant' if clean trade>",
  "key_lesson": "<one actionable sentence>",
  "adjusted_grade": "<A/B/C/D/F — your overall assessment>",
  "pattern_note": "<recurring pattern observation or 'No pattern detected'>",
  "coach_summary": "<one line trading coach style summary>"
}`;

app.post("/review-trade", async (c) => {
  const aigToken = c.env.CF_AIG_TOKEN;
  if (!aigToken) {
    return c.json({ ok: false, error: "CF_AIG_TOKEN not configured" }, 500);
  }

  const body = await c.req.json<ReviewTradeRequest>();

  const userPrompt = `Review this completed trade:

Ticker: ${body.ticker} (${body.direction})
Signal Score at Entry: ${body.signal_score}/100
Market State: ${body.market_state_at_entry} → ${body.market_state_at_exit}

Entry: $${body.entry_debit.toFixed(2)} debit
Exit: $${body.exit_credit.toFixed(2)} credit
P&L: ${(body.pnl_pct * 100).toFixed(1)}% ($${body.pnl_dollars.toFixed(2)})
Hold Duration: ${body.hold_duration_hours.toFixed(0)} hours
Exit Reason: ${body.exit_reason}

Mechanical Grades:
- Setup: ${body.setup_grade}
- Execution: ${body.execution_grade}
- Outcome: ${body.outcome_grade}

Failure Tags: ${body.failure_tags.length > 0 ? body.failure_tags.join(", ") : "None"}

Provide your coaching review as JSON.`;

  try {
    const text = await callClaude(aigToken, REVIEW_SYSTEM_PROMPT, userPrompt);
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      return c.json({ ok: false, error: "Failed to parse AI review", raw: text }, 500);
    }
    const review = JSON.parse(jsonMatch[0]);
    return c.json({ ok: true, review });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return c.json({ ok: false, error: msg }, 502);
  }
});

export default app;
