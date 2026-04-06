import pytest
from click.testing import CliRunner
from engine.cli import cli


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["version"])
    assert result.exit_code == 0
    assert "TTrade v" in result.output


def test_cli_status():
    runner = CliRunner()
    result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "TTrade Status" in result.output


def test_cli_approve_missing_id():
    runner = CliRunner()
    result = runner.invoke(cli, ["approve"])
    assert result.exit_code != 0
