"""Regression checks for public documentation command examples."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_ROOTS = [
    ROOT / "README.md",
    ROOT / "docs" / "mcp.md",
    ROOT / "docs-site" / "src" / "content",
]


def _doc_files() -> list[Path]:
    files: list[Path] = []
    for root in DOC_ROOTS:
        if root.is_file():
            files.append(root)
        else:
            files.extend(sorted(root.rglob("*.mdx")))
    return files


def _markdown_code_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    in_block = False
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("```"):
            if in_block:
                blocks.append("\n".join(current))
                current = []
                in_block = False
            else:
                in_block = True
            continue
        if in_block:
            current.append(line)
    return blocks


def _shell_commands(block: str) -> list[str]:
    commands: list[str] = []
    current = ""
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            current += line[:-1].strip() + " "
            continue
        current += line
        commands.append(re.sub(r"\s+", " ", current).strip())
        current = ""
    if current:
        commands.append(re.sub(r"\s+", " ", current).strip())
    return commands


def test_public_docs_do_not_use_private_runner_hooks() -> None:
    forbidden = ("._initialize(", "_session_seed", "agent_directory=")
    offenders: list[str] = []
    for path in _doc_files():
        text = path.read_text(encoding="utf8")
        for needle in forbidden:
            if needle in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {needle}")

    assert offenders == []


def test_forge_doctor_examples_do_not_pass_config_paths() -> None:
    pattern = re.compile(r"forge doctor\s+(?:\.|/|\w).*(?:aether-forge\.json|/)")
    offenders: list[str] = []
    for path in _doc_files():
        text = path.read_text(encoding="utf8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")

    assert offenders == []


def test_forge_migrate_examples_use_subcommands() -> None:
    offenders: list[str] = []
    for path in _doc_files():
        text = path.read_text(encoding="utf8")
        for block in _markdown_code_blocks(text):
            for command in _shell_commands(block):
                if command.startswith("forge migrate ") and not command.startswith(
                    ("forge migrate memory ", "forge migrate artifact ")
                ):
                    offenders.append(f"{path.relative_to(ROOT)}: {command}")

    assert offenders == []


def test_crypto_mode_examples_pin_policy_environment() -> None:
    offenders: list[str] = []
    for path in _doc_files():
        text = path.read_text(encoding="utf8")
        for block in _markdown_code_blocks(text):
            for command in _shell_commands(block):
                if "forge run " not in command:
                    continue
                if "--mode paper" in command and "--environment sandbox" not in command:
                    offenders.append(f"{path.relative_to(ROOT)}: {command}")
                if "--mode live" in command and "--environment production" not in command:
                    offenders.append(f"{path.relative_to(ROOT)}: {command}")

    assert offenders == []


def test_getting_started_starts_with_zero_risk_generation() -> None:
    text = (ROOT / "docs-site" / "src" / "content" / "getting-started.mdx").read_text(encoding="utf8")
    first_generate = text.index("forge generate-fast")
    first_run = text.index("forge run")

    first_generate_section = text[first_generate:first_run]
    assert "--planner-mode heuristic" in first_generate_section
    assert "--wallet" not in first_generate_section
    assert "--autonomous" not in first_generate_section
