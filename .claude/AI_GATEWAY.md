# AI Gateway Pattern — TTrade

> How this project calls AI models. Read this before touching any AI code.

## Rule

**All AI calls go through Cloudflare AI Gateway via the Workers AI binding.**

No API keys in code. No `CF_AIG_TOKEN`. No direct `fetch()` to `api.anthropic.com`.

## How It Works

```
Python engine → Worker /ai/* endpoint → env.AI.gateway("aicr").run() → AI Gateway → BYOK injects key → Anthropic
```

The `[ai] binding = "AI"` in `wrangler.toml` pre-authenticates the Worker to the gateway automatically. The `cf-aig-byok-alias: anthro-01` header tells the gateway to inject the stored Anthropic API key.

## Quick Reference

| Setting | Value |
|---------|-------|
| Gateway | `aicr` |
| Provider | `anthropic` |
| Endpoint | `v1/messages` |
| BYOK Alias | `anthro-01` |
| Model | `claude-haiku-4-5-20251001` |

## Code Location

- **Worker AI routes:** `worker/src/routes/ai.ts` — `callClaude()` helper
- **Engine analyst:** `engine/ai_analyst.py` — calls Worker `/ai/analyze`
- **Engine journal:** `engine/ai_journal.py` — calls Worker `/ai/review-trade`
- **News gate:** `engine/gates/news_sentiment.py` — calls Worker `/ai/analyze`

The Python engine never calls AI providers directly. It always goes through the Worker, which routes through the gateway.

## Do NOT

- Add `ANTHROPIC_API_KEY` to Worker secrets or engine env
- Call `api.anthropic.com` directly from any code
- Use `CF_AIG_TOKEN` — the binding handles auth
- Skip the gateway for "quick tests" — all calls must be logged

## Canonical Reference

Full gateway docs, provider switching, model tiers:
`~/Development/AICR/.claude/references/cloudflare-ai-gateway.md`
