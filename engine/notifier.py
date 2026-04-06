"""Notifications — iMessage (AppleScript) + Gmail (SMTP)."""
import logging
import smtplib
import subprocess
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def _get_keychain_value(service: str) -> str:
    result = subprocess.run(
        ["security", "find-generic-password", "-s", service, "-w"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Keychain lookup failed for {service}")
    return result.stdout.strip()


def format_signal_alert(
    ticker: str, direction: str, spread_desc: str, expiry: str, dte: int,
    debit: float, max_loss: int, max_gain: int, rr_ratio: float,
    signal_score: float, band: str, regime: str, confirmation: str, signal_id: str,
) -> str:
    spread_type = "Bull Call Spread" if direction == "bullish" else "Bear Put Spread"
    return (
        f"TTrade SIGNAL [{band}-setup, score: {signal_score:.0f}]\n\n"
        f"{ticker} {spread_type}\n{spread_desc}\n{expiry} exp ({dte} DTE)\n\n"
        f"Debit: ${debit:.2f} | Max loss: ${max_loss} | Max gain: ${max_gain}\n"
        f"R/R: {rr_ratio:.1f}:1\n\nRegime: {regime}\nConfirmation: {confirmation}\n\n"
        f"Run: ttrade approve {signal_id}"
    )


def format_exit_alert(
    ticker: str, direction: str, exit_reason: str, pnl_pct: float,
    entry_debit: float, exit_credit: float, pnl_dollars: float,
    mfe: float, mae: float, hold_days: int,
) -> str:
    spread_type = "Bull Call" if direction == "bullish" else "Bear Put"
    return (
        f"TTrade EXIT -- {ticker} {spread_type}\n\n{exit_reason} {pnl_pct:+.0f}%\n\n"
        f"Entry: ${entry_debit:.2f} -> Exit: ${exit_credit:.2f}\n"
        f"P&L: ${pnl_dollars:.2f}\n\nMFE: {mfe:+.0f}% | MAE: {mae:+.0f}%\n"
        f"Hold: {hold_days} days"
    )


def send_imessage(to: str, message: str) -> None:
    safe_message = message.replace('"', '\\"')
    script = (
        'tell application "Messages"\n'
        '    set targetService to 1st account whose service type = iMessage\n'
        f'    set targetBuddy to participant "{to}" of targetService\n'
        f'    send "{safe_message}" to targetBuddy\n'
        'end tell'
    )
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("iMessage send failed: %s", result.stderr)
        raise RuntimeError(f"iMessage failed: {result.stderr}")
    logger.info("iMessage sent to %s", to)


def send_gmail(to: str, subject: str, body: str, from_addr: str = "ttrade@aicoderally.com") -> None:
    app_password = _get_keychain_value("ttrade-GMAIL_APP_PASSWORD")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(from_addr, app_password)
        server.send_message(msg)
    logger.info("Email sent to %s: %s", to, subject)
