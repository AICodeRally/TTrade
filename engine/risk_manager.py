"""Position sizing, exposure buckets, strike selection."""
from engine.config import TTRadeConfig

MARKET_BUCKET = {"SPY", "QQQ"}
TECH_BUCKET = {"AAPL", "MSFT"}
SPECULATIVE_BUCKET = {"NVDA", "RKLB", "VCX"}


def get_exposure_bucket(ticker: str) -> str:
    if ticker in MARKET_BUCKET: return "market"
    if ticker in TECH_BUCKET: return "tech"
    if ticker in SPECULATIVE_BUCKET: return "speculative"
    return "other"


def calculate_position_size(account_value: float, iv_rank: float, config: TTRadeConfig) -> float:
    # Hard cap: never risk more than max_risk_per_trade_pct of account
    absolute_max = config.account_value * config.max_risk_per_trade_pct
    target = min(config.max_debit, absolute_max)
    if iv_rank > config.iv_rank_reduce_threshold:
        target *= 0.5
    return max(config.min_debit, min(target, absolute_max))


def select_strikes(chain: list[dict], direction: str, target_debit: float, config: TTRadeConfig) -> dict | None:
    option_type = "CALL" if direction == "bullish" else "PUT"
    options = [o for o in chain if o["type"] == option_type]
    options.sort(key=lambda x: x["strike"])
    best = None
    best_distance = float("inf")
    for i, buy_opt in enumerate(options):
        for sell_opt in options[i + 1:]:
            if direction == "bullish":
                buy_mid = (buy_opt["bid"] + buy_opt["ask"]) / 2
                sell_mid = (sell_opt["bid"] + sell_opt["ask"]) / 2
                net_debit = (buy_mid - sell_mid) * 100
            else:
                buy_mid = (sell_opt["bid"] + sell_opt["ask"]) / 2
                sell_mid = (buy_opt["bid"] + buy_opt["ask"]) / 2
                net_debit = (buy_mid - sell_mid) * 100
            if net_debit <= 0: continue
            spread_width = abs(sell_opt["strike"] - buy_opt["strike"])
            max_loss = net_debit
            max_gain = (spread_width * 100) - net_debit
            if max_gain <= 0: continue
            rr_ratio = max_gain / max_loss
            if rr_ratio < config.min_risk_reward: continue
            if buy_opt.get("oi", 0) < config.min_open_interest: continue
            if sell_opt.get("oi", 0) < config.min_open_interest: continue
            distance = abs(net_debit - target_debit)
            if distance < best_distance:
                best_distance = distance
                if direction == "bullish":
                    best = {"buy_strike": buy_opt["strike"], "sell_strike": sell_opt["strike"],
                            "net_debit": net_debit, "max_loss": max_loss, "max_gain": max_gain,
                            "spread_width": spread_width, "risk_reward_ratio": rr_ratio}
                else:
                    best = {"buy_strike": sell_opt["strike"], "sell_strike": buy_opt["strike"],
                            "net_debit": net_debit, "max_loss": max_loss, "max_gain": max_gain,
                            "spread_width": spread_width, "risk_reward_ratio": rr_ratio}
    return best
