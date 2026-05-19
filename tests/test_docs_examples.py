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


def _docs_routes() -> set[str]:
    content_root = ROOT / "docs-site" / "src" / "content"
    routes = {"/docs"}
    for path in content_root.rglob("*.mdx"):
        rel = path.relative_to(content_root).with_suffix("")
        route = "/docs/" + rel.as_posix()
        if route.endswith("/index"):
            route = route[: -len("/index")]
        routes.add(route)
    return routes


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


def test_internal_docs_links_include_docs_base_path() -> None:
    pattern = re.compile(r"\]\(/(guides|reference|cookbook|features|examples|help|getting-started)(?:[)#/?]|$)")
    offenders: list[str] = []
    for path in _doc_files():
        text = path.read_text(encoding="utf8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")

    assert offenders == []


def test_internal_docs_links_resolve_to_existing_pages() -> None:
    routes = _docs_routes()
    pattern = re.compile(r"\]\((/docs/[^)#?]+)")
    offenders: list[str] = []
    for path in _doc_files():
        text = path.read_text(encoding="utf8")
        for match in pattern.finditer(text):
            route = match.group(1).rstrip("/")
            if route not in routes:
                offenders.append(f"{path.relative_to(ROOT)}: {route}")

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


def test_docs_content_videos_are_lazy_accessible_and_stable() -> None:
    pattern = re.compile(r"<video\b(?P<attrs>[^>]*?)>", re.DOTALL)
    offenders: list[str] = []
    content_root = ROOT / "docs-site" / "src" / "content"
    for path in content_root.rglob("*.mdx"):
        text = path.read_text(encoding="utf8")
        for match in pattern.finditer(text):
            attrs = match.group("attrs")
            line_number = text[: match.start()].count("\n") + 1
            location = f"{path.relative_to(ROOT)}:{line_number}"
            if attrs.count("poster=") != 1:
                offenders.append(f"{location}: expected one poster attribute")
            if attrs.count("aria-label=") != 1:
                offenders.append(f"{location}: expected one aria-label attribute")
            if 'preload="none"' not in attrs:
                offenders.append(f"{location}: expected preload=\"none\"")

    assert offenders == []


def test_docs_video_assets_have_matching_posters() -> None:
    public_root = ROOT / "docs-site" / "public"
    videos_root = public_root / "videos"
    posters_root = public_root / "video-posters"
    offenders: list[str] = []

    for video in sorted(videos_root.glob("*.mp4")):
        poster = posters_root / f"{video.stem}.jpg"
        if not poster.is_file():
            offenders.append(f"missing poster for {video.relative_to(ROOT)}")

    pattern = re.compile(
        r'<video\b(?P<attrs>[^>]*?)\bsrc="(?P<src>/videos/[^"]+)"(?P<rest>[^>]*?)>',
        re.DOTALL,
    )
    docs_site_files = list((ROOT / "docs-site" / "src" / "content").rglob("*.mdx"))
    docs_site_files.append(ROOT / "docs-site" / "src" / "app" / "page.jsx")
    for path in docs_site_files:
        text = path.read_text(encoding="utf8")
        for match in pattern.finditer(text):
            attrs = match.group("attrs") + match.group("rest")
            src = match.group("src")
            source_path = public_root / src.removeprefix("/")
            if not source_path.is_file():
                offenders.append(f"{path.relative_to(ROOT)} references missing {src}")

            poster_match = re.search(r'poster="(?P<poster>/video-posters/[^"]+)"', attrs)
            if poster_match is None:
                offenders.append(f"{path.relative_to(ROOT)} video {src} has no poster")
                continue
            poster_path = public_root / poster_match.group("poster").removeprefix("/")
            if not poster_path.is_file():
                offenders.append(f"{path.relative_to(ROOT)} references missing {poster_match.group('poster')}")

    assert offenders == []
