from __future__ import annotations
import json
from pathlib import Path
from aether_forge.doctor import run_doctor_checks, validate_config, generate_default_config, CheckResult

def test_doctor_checks_return_results() -> None:
    results = run_doctor_checks()
    assert len(results) > 0
    assert all(isinstance(r, CheckResult) for r in results)
    # Python version check should pass since we're running on 3.12+
    python_check = next(r for r in results if r.name == "Python version")
    assert python_check.passed

def test_validate_config_valid(tmp_path: Path) -> None:
    config = {"planner": {"mode": "anthropic", "model": "claude-sonnet-4-20250514"}, "runtime": {"cryptoRouter": "mock"}}
    path = tmp_path / "aether-forge.json"
    path.write_text(json.dumps(config), encoding="utf8")
    results = validate_config(path)
    assert all(r.passed for r in results)

def test_validate_config_invalid_mode(tmp_path: Path) -> None:
    config = {"planner": {"mode": "nonexistent"}}
    path = tmp_path / "aether-forge.json"
    path.write_text(json.dumps(config), encoding="utf8")
    results = validate_config(path)
    failed = [r for r in results if not r.passed]
    assert len(failed) > 0

def test_validate_config_missing_file() -> None:
    results = validate_config(Path("/nonexistent/config.json"))
    assert not results[0].passed

def test_validate_config_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("not json{{{", encoding="utf8")
    results = validate_config(path)
    assert any(not r.passed for r in results)

def test_generate_default_config() -> None:
    config = generate_default_config(planner_mode="anthropic", planner_model="claude-sonnet-4-20250514", api_key_env="ANTHROPIC_API_KEY")
    assert config["planner"]["mode"] == "anthropic"
    assert config["planner"]["model"] == "claude-sonnet-4-20250514"
    assert config["planner"]["apiKeyEnv"] == "ANTHROPIC_API_KEY"

def test_init_cli_creates_config(tmp_path: Path) -> None:
    from aether_forge.cli import main
    output = tmp_path / "aether-forge.json"
    rc = main(["init", "--output", str(output), "--planner-mode", "openrouter"])
    assert rc == 0
    assert output.exists()
    data = json.loads(output.read_text(encoding="utf8"))
    assert data["planner"]["mode"] == "openrouter"

def test_config_validate_cli(tmp_path: Path) -> None:
    from aether_forge.cli import main
    config = tmp_path / "aether-forge.json"
    config.write_text(json.dumps({"planner": {"mode": "ollama"}}), encoding="utf8")
    rc = main(["config-validate", str(config)])
    assert rc == 0
