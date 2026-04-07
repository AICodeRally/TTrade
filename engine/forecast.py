"""Price forecasting — ARIMA + Fourier + technical features.

Three-layer forecast:
1. ARIMA — captures short-term autoregressive momentum
2. Fourier Transform — extracts cyclical patterns (3, 6, 9 harmonics)
3. Ensemble — blends ARIMA + Fourier + TA features via Ridge regression

Outputs a directional forecast with confidence, used to bias
grid spacing and trade direction.
"""
import logging
import warnings
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning, module="statsmodels")
warnings.filterwarnings("ignore", message=".*ConvergenceWarning.*")

from statsmodels.tsa.arima.model import ARIMA
from pmdarima.arima import auto_arima
from sklearn.linear_model import Ridge
from sklearn.preprocessing import MinMaxScaler

from engine.market_data import compute_sma, compute_atr

logger = logging.getLogger(__name__)


@dataclass
class ForecastResult:
    ticker: str
    current_price: float
    # ARIMA
    arima_order: tuple[int, int, int]
    arima_forecast_5d: list[float]
    arima_direction: str        # "up", "down", "flat"
    arima_change_pct: float
    # Fourier
    fourier_dominant_period: int  # days
    fourier_forecast_5d: list[float]
    fourier_direction: str
    fourier_change_pct: float
    fourier_cycle_position: str  # "rising", "peak", "falling", "trough"
    # Ensemble
    ensemble_forecast_5d: list[float]
    ensemble_direction: str
    ensemble_change_pct: float
    ensemble_confidence: float   # 0-100
    # Forecast summary
    predicted_price_5d: float
    predicted_change_pct: float
    direction: str               # "BULLISH", "BEARISH", "NEUTRAL"
    strength: str                # "strong", "moderate", "weak"
    # Model quality
    arima_mape: float
    ensemble_mape: float
    # Grid bias
    grid_bias: str               # "long", "short", "neutral"
    suggested_grid_shift_pct: float  # shift grid center by this %
    timestamp: datetime


def _fetch_history(ticker: str, period_days: int = 365) -> pd.DataFrame:
    """Fetch daily bars for forecasting."""
    import yfinance as yf
    data = yf.download(ticker, period=f"{period_days}d", interval="1d", progress=False)
    if data.empty:
        raise ValueError(f"No data for {ticker}")
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)
    return data


def _compute_ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def _compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=period).mean()
    loss = (-delta).clip(lower=0).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def _compute_macd(close: pd.Series) -> pd.Series:
    ema12 = _compute_ema(close, 12)
    ema26 = _compute_ema(close, 26)
    return ema12 - ema26


def _compute_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.where(close > close.shift(), 1,
                         np.where(close < close.shift(), -1, 0))
    return (direction * volume).cumsum()


# ── ARIMA Layer ──

def _fit_arima(close: pd.Series, forecast_days: int = 5) -> tuple:
    """Fit ARIMA model and forecast.

    Returns (order, forecast_values, mape).
    """
    values = close.values.astype(float)

    # Auto-select ARIMA order
    try:
        model = auto_arima(
            values, seasonal=False, trace=False,
            suppress_warnings=True, stepwise=True,
            max_p=3, max_q=3, max_d=2,
        )
        order = model.order
    except Exception:
        order = (1, 1, 0)

    # Walk-forward validation on last 20% for MAPE
    split = int(len(values) * 0.8)
    train, test = values[:split], values[split:]

    predictions = []
    history = list(train)
    for t in range(min(len(test), 30)):  # cap validation to 30 steps
        try:
            m = ARIMA(history, order=order)
            fit = m.fit()
            yhat = float(fit.forecast()[0])
            predictions.append(yhat)
            history.append(test[t])
        except Exception:
            predictions.append(history[-1])
            history.append(test[t])

    # MAPE
    if predictions and len(test) >= len(predictions):
        actual = test[:len(predictions)]
        mape = float(np.mean(np.abs((actual - np.array(predictions)) / actual)) * 100)
    else:
        mape = 999.0

    # Forecast forward
    try:
        full_model = ARIMA(values, order=order)
        full_fit = full_model.fit()
        forecast = full_fit.forecast(steps=forecast_days)
        forecast_values = [round(float(v), 2) for v in forecast]
    except Exception:
        forecast_values = [round(float(values[-1]), 2)] * forecast_days

    return order, forecast_values, round(mape, 2)


# ── Fourier Layer ──

def _fit_fourier(close: pd.Series, forecast_days: int = 5, n_harmonics: int = 9) -> tuple:
    """Extract cyclical patterns via FFT and extrapolate.

    Returns (dominant_period, forecast_values, cycle_position).
    """
    values = close.values.astype(float)
    n = len(values)

    # FFT
    fft = np.fft.fft(values)
    freqs = np.fft.fftfreq(n)

    # Find dominant frequency (skip DC component at index 0)
    magnitudes = np.abs(fft[1:n // 2])
    dominant_idx = np.argmax(magnitudes) + 1
    dominant_freq = abs(freqs[dominant_idx])
    dominant_period = int(1 / dominant_freq) if dominant_freq > 0 else n

    # Reconstruct using top harmonics
    fft_filtered = np.copy(fft)
    # Zero out all but top n_harmonics frequencies
    magnitude_order = np.argsort(np.abs(fft))[::-1]
    keep = set(magnitude_order[:n_harmonics * 2 + 1])  # + DC and mirror
    for i in range(len(fft_filtered)):
        if i not in keep:
            fft_filtered[i] = 0

    # Reconstruct in-sample
    reconstructed = np.real(np.fft.ifft(fft_filtered))

    # Extrapolate by extending the signal
    # Use the last cycle pattern to project forward
    cycle_len = min(dominant_period, n // 2)
    cycle_len = max(cycle_len, 5)  # at least 5 days

    # Linear detrend to isolate cycle
    x = np.arange(n)
    slope = np.polyfit(x, values, 1)
    trend_line = np.polyval(slope, x)
    detrended = values - trend_line

    # Project trend forward
    future_x = np.arange(n, n + forecast_days)
    future_trend = np.polyval(slope, future_x)

    # Project cycle forward using last cycle
    last_cycle = detrended[-cycle_len:]
    cycle_projection = []
    for i in range(forecast_days):
        cycle_projection.append(last_cycle[i % cycle_len])

    forecast_values = [round(float(future_trend[i] + cycle_projection[i]), 2)
                       for i in range(forecast_days)]

    # Cycle position: are we rising or falling in the current cycle?
    recent_recon = reconstructed[-10:]
    if len(recent_recon) >= 3:
        last_slope = recent_recon[-1] - recent_recon[-3]
        is_near_peak = recent_recon[-1] > np.percentile(reconstructed, 75)
        is_near_trough = recent_recon[-1] < np.percentile(reconstructed, 25)

        if is_near_peak:
            cycle_pos = "peak"
        elif is_near_trough:
            cycle_pos = "trough"
        elif last_slope > 0:
            cycle_pos = "rising"
        else:
            cycle_pos = "falling"
    else:
        cycle_pos = "rising"

    return dominant_period, forecast_values, cycle_pos


# ── Ensemble Layer ──

def _build_features(bars: pd.DataFrame) -> pd.DataFrame:
    """Build feature matrix from technical indicators."""
    close = bars["Close"]
    volume = bars["Volume"]

    features = pd.DataFrame(index=bars.index)
    features["close"] = close
    features["returns_1d"] = close.pct_change()
    features["returns_5d"] = close.pct_change(5)
    features["sma_20_dist"] = (close - compute_sma(close, 20)) / compute_sma(close, 20)
    features["sma_50_dist"] = (close - compute_sma(close, 50)) / compute_sma(close, 50)
    features["ema_12"] = _compute_ema(close, 12)
    features["ema_26"] = _compute_ema(close, 26)
    features["rsi"] = _compute_rsi(close)
    features["macd"] = _compute_macd(close)
    features["obv"] = _compute_obv(close, volume)

    atr = compute_atr(bars, period=14)
    features["atr_pct"] = atr / close

    # Bollinger Band position
    sma20 = compute_sma(close, 20)
    std20 = close.rolling(window=20).std()
    features["bb_position"] = (close - sma20) / (2 * std20)

    # Volume ratio
    features["vol_ratio"] = volume / volume.rolling(20).mean()

    # Stochastic
    high14 = bars["High"].rolling(14).max()
    low14 = bars["Low"].rolling(14).min()
    features["stoch_k"] = (close - low14) / (high14 - low14) * 100

    return features.dropna()


def _fit_ensemble(
    bars: pd.DataFrame,
    arima_forecast: list[float],
    fourier_forecast: list[float],
    forecast_days: int = 5,
) -> tuple[list[float], float]:
    """Blend ARIMA + Fourier + TA features via Ridge regression.

    Returns (forecast_values, mape).
    """
    features = _build_features(bars)
    close = features["close"].values

    # Target: 5-day forward return
    target = pd.Series(close, index=features.index).pct_change(forecast_days).shift(-forecast_days)
    valid_mask = target.notna()
    X = features.loc[valid_mask].drop(columns=["close"]).values
    y = target.loc[valid_mask].values

    if len(X) < 50:
        # Not enough data — fall back to simple average
        avg = [(a + f) / 2 for a, f in zip(arima_forecast, fourier_forecast)]
        return avg, 999.0

    # Scale features
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X)

    # Train/test split (80/20)
    split = int(len(X_scaled) * 0.8)
    X_train, X_test = X_scaled[:split], X_scaled[split:]
    y_train, y_test = y[:split], y[split:]

    # Fit Ridge regression
    model = Ridge(alpha=1.0)
    model.fit(X_train, y_train)

    # Validate
    y_pred = model.predict(X_test)
    mape = float(np.mean(np.abs((y_test - y_pred) / (y_test + 1e-8))) * 100)
    mape = min(mape, 999.0)

    # Predict from latest features
    latest_features = features.iloc[-1:].drop(columns=["close"]).values
    latest_scaled = scaler.transform(latest_features)
    predicted_return = float(model.predict(latest_scaled)[0])

    current_price = float(close[-1])
    # Blend: 40% ensemble, 30% ARIMA, 30% Fourier
    ensemble_forecast = []
    for i in range(forecast_days):
        # Interpolate the predicted return across days
        day_return = predicted_return * (i + 1) / forecast_days
        ensemble_price = current_price * (1 + day_return)

        arima_price = arima_forecast[i] if i < len(arima_forecast) else arima_forecast[-1]
        fourier_price = fourier_forecast[i] if i < len(fourier_forecast) else fourier_forecast[-1]

        blended = 0.40 * ensemble_price + 0.30 * arima_price + 0.30 * fourier_price
        ensemble_forecast.append(round(blended, 2))

    return ensemble_forecast, round(mape, 2)


def forecast_price(ticker: str, forecast_days: int = 5) -> ForecastResult:
    """Run full three-layer price forecast."""
    bars = _fetch_history(ticker, period_days=365)
    close = bars["Close"]
    current_price = float(close.iloc[-1])

    # Layer 1: ARIMA
    logger.info("Fitting ARIMA for %s...", ticker)
    arima_order, arima_fc, arima_mape = _fit_arima(close, forecast_days)
    arima_change = (arima_fc[-1] - current_price) / current_price * 100
    arima_dir = "up" if arima_change > 0.5 else "down" if arima_change < -0.5 else "flat"

    # Layer 2: Fourier
    logger.info("Fitting Fourier for %s...", ticker)
    dominant_period, fourier_fc, cycle_pos = _fit_fourier(close, forecast_days)
    fourier_change = (fourier_fc[-1] - current_price) / current_price * 100
    fourier_dir = "up" if fourier_change > 0.5 else "down" if fourier_change < -0.5 else "flat"

    # Layer 3: Ensemble
    logger.info("Fitting ensemble for %s...", ticker)
    ensemble_fc, ensemble_mape = _fit_ensemble(bars, arima_fc, fourier_fc, forecast_days)
    ensemble_change = (ensemble_fc[-1] - current_price) / current_price * 100
    ensemble_dir = "up" if ensemble_change > 0.5 else "down" if ensemble_change < -0.5 else "flat"

    # Composite direction
    votes = {"up": 0, "down": 0, "flat": 0}
    for d in [arima_dir, fourier_dir, ensemble_dir]:
        votes[d] += 1

    if votes["up"] >= 2:
        direction = "BULLISH"
    elif votes["down"] >= 2:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    # Strength from agreement and magnitude
    agreement = max(votes.values()) / 3
    magnitude = abs(ensemble_change)
    if agreement >= 0.67 and magnitude > 2:
        strength = "strong"
    elif agreement >= 0.67 or magnitude > 1:
        strength = "moderate"
    else:
        strength = "weak"

    # Confidence from model quality
    confidence = max(0, min(100, 100 - arima_mape * 2))
    if ensemble_mape < 50:
        confidence = min(100, confidence + 15)

    # Grid bias: how to shift the grid
    if direction == "BULLISH" and strength in ("strong", "moderate"):
        grid_bias = "long"
        grid_shift = min(ensemble_change * 0.3, 3.0)  # shift center up by 30% of expected move
    elif direction == "BEARISH" and strength in ("strong", "moderate"):
        grid_bias = "short"
        grid_shift = max(ensemble_change * 0.3, -3.0)
    else:
        grid_bias = "neutral"
        grid_shift = 0.0

    return ForecastResult(
        ticker=ticker,
        current_price=round(current_price, 2),
        arima_order=arima_order,
        arima_forecast_5d=arima_fc,
        arima_direction=arima_dir,
        arima_change_pct=round(arima_change, 2),
        fourier_dominant_period=dominant_period,
        fourier_forecast_5d=fourier_fc,
        fourier_direction=fourier_dir,
        fourier_change_pct=round(fourier_change, 2),
        fourier_cycle_position=cycle_pos,
        ensemble_forecast_5d=ensemble_fc,
        ensemble_direction=ensemble_dir,
        ensemble_change_pct=round(ensemble_change, 2),
        ensemble_confidence=round(confidence, 1),
        predicted_price_5d=round(ensemble_fc[-1], 2),
        predicted_change_pct=round(ensemble_change, 2),
        direction=direction,
        strength=strength,
        arima_mape=arima_mape,
        ensemble_mape=ensemble_mape,
        grid_bias=grid_bias,
        suggested_grid_shift_pct=round(grid_shift, 2),
        timestamp=datetime.now(),
    )
