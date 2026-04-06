import pytest
from unittest.mock import patch, MagicMock
from engine.notifier import format_signal_alert, format_exit_alert, send_imessage, send_gmail


def test_format_signal_alert():
    msg = format_signal_alert(
        ticker="QQQ", direction="bearish", spread_desc="Buy 440P / Sell 435P",
        expiry="Jun 20", dte=45, debit=0.72, max_loss=72, max_gain=428,
        rr_ratio=5.9, signal_score=87.0, band="A", regime="TREND_DOWN (strong)",
        confirmation="lower high + breakdown + volume", signal_id="sig_abc12345",
    )
    assert "TTrade SIGNAL" in msg
    assert "QQQ" in msg
    assert "Bear Put Spread" in msg
    assert "sig_abc12345" in msg
    assert "ttrade approve" in msg


def test_format_exit_alert():
    msg = format_exit_alert(
        ticker="QQQ", direction="bearish", exit_reason="PROFIT TARGET HIT",
        pnl_pct=68.0, entry_debit=0.72, exit_credit=1.21, pnl_dollars=49.0,
        mfe=71.0, mae=-12.0, hold_days=8,
    )
    assert "TTrade EXIT" in msg
    assert "PROFIT TARGET" in msg
    assert "$49.00" in msg


@patch("engine.notifier.subprocess.run")
def test_send_imessage(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    send_imessage("+15551234567", "Test message")
    mock_run.assert_called_once()
    call_args = mock_run.call_args
    assert "osascript" in call_args[0][0]


@patch("engine.notifier.smtplib.SMTP_SSL")
@patch("engine.notifier._get_keychain_value")
def test_send_gmail(mock_keychain, mock_smtp):
    mock_keychain.return_value = "app_password_123"
    mock_server = MagicMock()
    mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
    send_gmail(to="todd@aicoderally.com", subject="TTrade Daily", body="Test body",
               from_addr="ttrade@aicoderally.com")
    mock_server.send_message.assert_called_once()
