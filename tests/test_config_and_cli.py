from __future__ import annotations

from pathlib import Path

from droidpilot import __main__ as cli
from droidpilot.config import DEFAULT_OLLAMA_MODEL, Config
from droidpilot.doctor import Check, format_report


def test_config_from_env_defaults():
    config = Config.from_env({})
    assert config.ollama_model == DEFAULT_OLLAMA_MODEL
    assert config.sdk_root is None


def test_config_from_env_overrides():
    env = {
        "ANDROID_HOME": "/opt/sdk",
        "DROIDPILOT_OLLAMA_MODEL": "qwen2",
        "DROIDPILOT_SCREEN_REFRESH_MS": "250",
    }
    config = Config.from_env(env)
    assert config.sdk_root == Path("/opt/sdk")
    assert config.ollama_model == "qwen2"
    assert config.screen_refresh_ms == 250


def test_format_report():
    checks = [Check("A", True, "good"), Check("B", False, "bad")]
    report = format_report(checks)
    assert "[OK ] A: good" in report
    assert "[!! ] B: bad" in report


def test_cli_doctor(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_checks", lambda config: [Check("SDK", True, "/sdk")])
    code = cli.main(["doctor"])
    assert code == 0
    assert "SDK" in capsys.readouterr().out


def test_cli_doctor_nonzero_on_failure(monkeypatch):
    monkeypatch.setattr(cli, "run_checks", lambda config: [Check("SDK", False, "missing")])
    assert cli.main(["doctor"]) == 1


def test_build_parser_has_subcommands():
    parser = cli.build_parser()
    args = parser.parse_args(["doctor"])
    assert args.command == "doctor"
