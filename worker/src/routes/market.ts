import { Hono } from "hono";
import { Env } from "../types";

const AUTH_URL =
  "https://api.public.com/userapiauthservice/personal/access-tokens";
const MARKET_URL = "https://api.public.com/userapigateway/marketdata";

const app = new Hono<{ Bindings: Env }>();

async function getAccessToken(secret: string): Promise<string> {
  const resp = await fetch(AUTH_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ validityInMinutes: 60, secret }),
  });
  if (!resp.ok) throw new Error(`Auth failed: ${resp.status}`);
  const data = (await resp.json()) as { accessToken: string };
  return data.accessToken;
}

app.get("/quotes", async (c) => {
  const accountId = c.env.PUBLIC_ACCOUNT_ID;
  const secret = c.env.PUBLIC_API_SECRET;

  if (!secret || !accountId) {
    return c.json({ ok: false, error: "Broker credentials not configured" }, 500);
  }

  const custom = c.req.query("symbols");
  const tickers = custom ? custom.split(",") : ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"];

  const token = await getAccessToken(secret);

  const resp = await fetch(`${MARKET_URL}/${accountId}/quotes`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      instruments: tickers.map((s) => ({ symbol: s, type: "EQUITY" })),
    }),
  });

  if (!resp.ok) {
    return c.json({ ok: false, error: `Quotes API: ${resp.status}` }, 502);
  }

  const data = (await resp.json()) as { quotes: unknown[] };

  return c.json({ ok: true, quotes: data.quotes });
});

app.get("/options/:symbol", async (c) => {
  const accountId = c.env.PUBLIC_ACCOUNT_ID;
  const secret = c.env.PUBLIC_API_SECRET;
  const symbol = c.req.param("symbol").toUpperCase();

  if (!secret || !accountId) {
    return c.json({ ok: false, error: "Broker credentials not configured" }, 500);
  }

  const token = await getAccessToken(secret);
  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

  // Get expirations
  const expResp = await fetch(`${MARKET_URL}/${accountId}/option-expirations`, {
    method: "POST",
    headers,
    body: JSON.stringify({ instrument: { symbol, type: "EQUITY" } }),
  });
  if (!expResp.ok) return c.json({ ok: false, error: `Expirations: ${expResp.status}` }, 502);
  const expData = (await expResp.json()) as { expirations: string[] };

  // Get chain for nearest expiration
  const nearest = expData.expirations[0];
  if (!nearest) return c.json({ ok: true, expirations: [], chain: null });

  const chainResp = await fetch(`${MARKET_URL}/${accountId}/option-chain`, {
    method: "POST",
    headers,
    body: JSON.stringify({ instrument: { symbol, type: "EQUITY" }, expirationDate: nearest }),
  });
  if (!chainResp.ok) return c.json({ ok: false, error: `Chain: ${chainResp.status}` }, 502);
  const chainData = await chainResp.json();

  return c.json({ ok: true, expirations: expData.expirations, expiration: nearest, chain: chainData });
});

app.get("/chart/:symbol", async (c) => {
  const symbol = c.req.param("symbol").toUpperCase();
  const range = c.req.query("range") || "1mo";
  const interval = c.req.query("interval") || (range === "1d" ? "5m" : range === "5d" ? "15m" : "1d");

  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${symbol}?range=${range}&interval=${interval}&includePrePost=false`;
  const resp = await fetch(url, { headers: { "User-Agent": "TTrade/1.1" } });
  if (!resp.ok) return c.json({ ok: false, error: `Yahoo: ${resp.status}` }, 502);

  const data = (await resp.json()) as {
    chart: { result: Array<{
      meta: Record<string, unknown>;
      timestamp: number[];
      indicators: { quote: Array<{ open: number[]; high: number[]; low: number[]; close: number[]; volume: number[] }> };
    }> };
  };

  const result = data.chart?.result?.[0];
  if (!result) return c.json({ ok: false, error: "No chart data" }, 404);

  return c.json({
    ok: true,
    symbol,
    range,
    interval,
    meta: result.meta,
    timestamps: result.timestamp,
    ohlcv: result.indicators?.quote?.[0],
  });
});

app.get("/news/:symbol", async (c) => {
  const symbol = c.req.param("symbol").toUpperCase();

  // Try Google News RSS for stock news
  const query = encodeURIComponent(`${symbol} stock`);
  const url = `https://news.google.com/rss/search?q=${query}&hl=en-US&gl=US&ceid=US:en`;
  const resp = await fetch(url);
  if (!resp.ok) return c.json({ ok: true, articles: [] });

  const xml = await resp.text();

  const articles: Array<{ title: string; link: string; pubDate: string; source: string }> = [];
  const itemRegex = /<item>([\s\S]*?)<\/item>/g;
  let m;
  while ((m = itemRegex.exec(xml)) !== null && articles.length < 8) {
    const item = m[1];
    const title = item.match(/<title>([\s\S]*?)<\/title>/)?.[1]?.replace(/<!\[CDATA\[([\s\S]*?)\]\]>/, "$1") || "";
    const link = item.match(/<link>([\s\S]*?)<\/link>/)?.[1] || "";
    const pubDate = item.match(/<pubDate>([\s\S]*?)<\/pubDate>/)?.[1] || "";
    const source = item.match(/<source[^>]*>([\s\S]*?)<\/source>/)?.[1] || "";
    articles.push({ title, link, pubDate, source });
  }

  return c.json({ ok: true, articles });
});

app.get("/portfolio", async (c) => {
  const accountId = c.env.PUBLIC_ACCOUNT_ID;
  const secret = c.env.PUBLIC_API_SECRET;

  if (!secret || !accountId) {
    return c.json({ ok: false, error: "Broker credentials not configured" }, 500);
  }

  const token = await getAccessToken(secret);

  const resp = await fetch(
    `https://api.public.com/userapigateway/trading/${accountId}/portfolio/v2`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
    }
  );

  if (!resp.ok) {
    return c.json({ ok: false, error: `Portfolio API: ${resp.status}` }, 502);
  }

  const data = await resp.json();
  return c.json({ ok: true, portfolio: data });
});

export default app;
