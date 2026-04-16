"""Terminal dashboard for the two-agent marketplace.

Pure stdlib — no Flask, no curses. Refreshes every 2s. Shows live state
of both agents: address, ticks, readiness, on-chain ETH/USDC balances,
and the last 10 audit events.

Usage:
    DEMO_DIR=/tmp/two-agent-marketplace python3 terminal-dashboard.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path

DEMO_DIR = Path(os.environ.get("DEMO_DIR", "/tmp/two-agent-marketplace"))
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
RPC = os.environ.get("RPC", "https://mainnet.base.org")

# ANSI codes
CLEAR = "\033[2J\033[H"
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"
WHITE = "\033[37m"


def _wallet_address(agent_dir: Path) -> str:
    if not (agent_dir / "wallet.json").exists():
        return ""
    cfg = json.loads((agent_dir / "wallet.json").read_text())
    accounts = cfg.get("accounts", []) or cfg.get("addresses", {})
    if isinstance(accounts, dict):
        return accounts.get("evm", "")
    evm = next((a for a in accounts if a.get("chain") == "evm"), None)
    return evm["address"] if evm else ""


def _http_json(url: str, timeout: float = 1.5) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return {}


def _audit(agent_dir: Path) -> list[dict]:
    p = agent_dir / "x402_audit.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out[-10:]


def _balance(addr: str, asset: str) -> float:
    if not addr:
        return 0.0
    try:
        if asset == "ETH":
            body = json.dumps({"jsonrpc": "2.0", "id": 1,
                               "method": "eth_getBalance",
                               "params": [addr, "latest"]}).encode()
        else:
            slot = addr.lower().replace("0x", "").rjust(64, "0")
            body = json.dumps({"jsonrpc": "2.0", "id": 1,
                               "method": "eth_call",
                               "params": [{"to": USDC_BASE,
                                           "data": "0x70a08231" + slot},
                                          "latest"]}).encode()
        req = urllib.request.Request(RPC, data=body,
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as r:
            res = json.loads(r.read()).get("result", "0x0")
        raw = int(res, 16)
        return raw / 1e18 if asset == "ETH" else raw / 1e6
    except Exception:
        return 0.0


def _color_event(event: str) -> str:
    if "settled" in event:
        return GREEN
    if "failed" in event or "denied" in event or "rejected" in event:
        return RED
    if "attempted" in event or "received" in event:
        return BLUE
    return YELLOW


def render() -> str:
    width = shutil.get_terminal_size().columns
    half = (width - 3) // 2

    lines = [CLEAR]
    lines.append(f"{BOLD}{CYAN}  TWO-AGENT MARKETPLACE — live dashboard{RESET}")
    lines.append(DIM + "  " + ("─" * (width - 4)) + RESET)
    lines.append("")

    snap = {}
    for role, port in [("BUYER", 8001), ("ORACLE", 8002)]:
        agent_dir = DEMO_DIR / role.lower()
        addr = _wallet_address(agent_dir)
        status = _http_json(f"http://localhost:{port}/status")
        ready = _http_json(f"http://localhost:{port}/ready")
        snap[role] = {
            "dir": agent_dir,
            "addr": addr,
            "status": status,
            "ready": ready,
            "audit": _audit(agent_dir),
            "eth": _balance(addr, "ETH"),
            "usdc": _balance(addr, "USDC"),
        }

    # Two-column header
    def header(role: str) -> str:
        s = snap[role]
        running = s["status"].get("status") == "running"
        ready = s["ready"].get("ready", False)
        dot = (GREEN + "●" + RESET) if (running and ready) else (RED + "●" + RESET)
        title = f"{dot} {BOLD}{role}{RESET}"
        sub = (s["status"].get("status") or "down")
        return f"{title:30s}  {DIM}{sub}{RESET}"

    lines.append(f"  {header('BUYER'):<{half + 30}}  {header('ORACLE')}")

    # Address
    def line(label: str, b_val: str, o_val: str, color: str = "") -> str:
        b = f"{DIM}{label}{RESET}  {color}{b_val}{RESET}"
        o = f"{DIM}{label}{RESET}  {color}{o_val}{RESET}"
        return f"  {b:<{half + 30}}  {o}"

    lines.append(line("addr ", snap["BUYER"]["addr"][:42], snap["ORACLE"]["addr"][:42]))
    lines.append(line("ticks",
                      str(snap["BUYER"]["status"].get("ticks_completed", 0)),
                      str(snap["ORACLE"]["status"].get("ticks_completed", 0))))

    # Balances
    eth_b = f"{snap['BUYER']['eth']:.6f} ETH"
    eth_o = f"{snap['ORACLE']['eth']:.6f} ETH"
    usdc_b = f"${snap['BUYER']['usdc']:.4f} USDC"
    usdc_o = f"${snap['ORACLE']['usdc']:.4f} USDC"
    lines.append(line("ETH  ", eth_b, eth_o, BLUE))
    lines.append(line("USDC ", usdc_b, usdc_o, GREEN))

    # Readiness reason
    rb = snap["BUYER"]["ready"].get("reason", "?")
    ro = snap["ORACLE"]["ready"].get("reason", "?")
    lines.append(line("ready", rb[:30], ro[:30]))

    lines.append("")
    lines.append(f"  {DIM}── recent audit events ──{RESET}")
    lines.append("")

    # Combined audit feed
    combined = []
    for role in ("BUYER", "ORACLE"):
        for e in snap[role]["audit"]:
            combined.append((e.get("timestamp", ""), role, e))
    combined.sort(key=lambda x: x[0], reverse=True)
    combined = combined[:14]

    if not combined:
        lines.append(f"  {DIM}(no audit events yet){RESET}")
    else:
        for ts, role, evt in combined:
            event = evt.get("event", "?")
            amt = evt.get("amount_usd")
            amt_str = f"${amt}" if amt is not None else ""
            color = _color_event(event)
            time_str = ts[11:19] if len(ts) >= 19 else ts
            tx = evt.get("tx_hash", "")[:14] + "..." if evt.get("tx_hash") else ""
            line_out = (f"  {DIM}{time_str}{RESET}  "
                        f"{color}{role:<7}{RESET}  "
                        f"{color}{event:<22}{RESET}  "
                        f"{BLUE}{amt_str:<10}{RESET}  "
                        f"{DIM}{tx}{RESET}")
            lines.append(line_out)

    lines.append("")
    lines.append(DIM + "  " + ("─" * (width - 4)) + RESET)
    lines.append(f"  {DIM}refresh: 2s · DEMO_DIR={DEMO_DIR} · RPC={RPC}{RESET}")
    lines.append(f"  {DIM}Ctrl+C to exit · trigger payment: python3 pay-once.py{RESET}")

    return "\n".join(lines) + "\n"


def main() -> None:
    try:
        while True:
            sys.stdout.write(render())
            sys.stdout.flush()
            time.sleep(2)
    except KeyboardInterrupt:
        sys.stdout.write(RESET + "\n  exited.\n")


if __name__ == "__main__":
    main()
