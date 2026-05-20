"""Two-Agent Marketplace dashboard.

Live web UI that scrapes /metrics, /status, x402_audit.jsonl, and on-chain
balances from both agents.

Run after `./setup.sh` has generated the agents:

    pip install flask requests
    python3 dashboard.py
    open http://localhost:5000
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

try:
    from flask import Flask, jsonify, render_template_string
except ImportError:
    raise SystemExit("pip install flask requests")

DEMO_DIR = Path(os.environ.get("DEMO_DIR", "/tmp/two-agent-marketplace"))
BUYER_DIR = DEMO_DIR / "buyer"
ORACLE_DIR = DEMO_DIR / "oracle"
BUYER_HEALTH = "http://localhost:8001"
ORACLE_HEALTH = "http://localhost:8002"

USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
RPC = "https://mainnet.base.org"

app = Flask(__name__)


def _wallet_address(agent_dir: Path) -> str:
    cfg = json.loads((agent_dir / "wallet.json").read_text())
    accounts = cfg.get("accounts", []) or cfg.get("addresses", {})
    if isinstance(accounts, dict):
        return accounts.get("evm", "")
    evm = next((a for a in accounts if a.get("chain") == "evm"), None)
    return evm["address"] if evm else ""


def _http_json(url: str, timeout: float = 2) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"_error": str(e)}


def _http_text(url: str, timeout: float = 2) -> str:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read().decode()
    except Exception as e:
        return f"_error: {e}"


def _read_audit(agent_dir: Path) -> list[dict]:
    audit = agent_dir / "x402_audit.jsonl"
    if not audit.exists():
        return []
    out = []
    for line in audit.read_text().splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out[-30:]  # latest 30


def _on_chain_balance(address: str, asset: str = "USDC") -> float:
    if not address:
        return 0.0
    try:
        if asset == "ETH":
            body = json.dumps({
                "jsonrpc": "2.0", "id": 1,
                "method": "eth_getBalance",
                "params": [address, "latest"],
            }).encode()
        else:  # USDC
            slot = address.lower().replace("0x", "").rjust(64, "0")
            body = json.dumps({
                "jsonrpc": "2.0", "id": 1,
                "method": "eth_call",
                "params": [{"to": USDC_BASE, "data": "0x70a08231" + slot}, "latest"],
            }).encode()
        req = urllib.request.Request(RPC, data=body,
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=4) as r:
            res = json.loads(r.read()).get("result", "0x0")
        raw = int(res, 16)
        if asset == "ETH":
            return raw / 1e18
        return raw / 1e6
    except Exception:
        return 0.0


@app.route("/api/state")
def state():
    buyer_addr = _wallet_address(BUYER_DIR) if BUYER_DIR.exists() else ""
    oracle_addr = _wallet_address(ORACLE_DIR) if ORACLE_DIR.exists() else ""
    return jsonify({
        "buyer": {
            "dir": str(BUYER_DIR),
            "address": buyer_addr,
            "status": _http_json(f"{BUYER_HEALTH}/status"),
            "ready": _http_json(f"{BUYER_HEALTH}/ready"),
            "audit": _read_audit(BUYER_DIR),
            "eth_balance": _on_chain_balance(buyer_addr, "ETH"),
            "usdc_balance": _on_chain_balance(buyer_addr, "USDC"),
        },
        "oracle": {
            "dir": str(ORACLE_DIR),
            "address": oracle_addr,
            "status": _http_json(f"{ORACLE_HEALTH}/status"),
            "ready": _http_json(f"{ORACLE_HEALTH}/ready"),
            "audit": _read_audit(ORACLE_DIR),
            "eth_balance": _on_chain_balance(oracle_addr, "ETH"),
            "usdc_balance": _on_chain_balance(oracle_addr, "USDC"),
        },
        "now": time.time(),
    })


_TEMPLATE = """
<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<title>Two-Agent Marketplace</title>
<style>
  body { font: 14px -apple-system, BlinkMacSystemFont, sans-serif; background:#0a0a0a; color:#e5e5e7; margin:0; padding:24px; }
  h1 { font-weight:800; letter-spacing:.04em; margin:0 0 24px; font-size:28px; }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:24px; }
  .card { background:#141416; border:1px solid #2a2a2e; border-radius:14px; padding:18px; }
  .card h2 { margin:0 0 12px; font-size:18px; color:#f5f5f7; display:flex; align-items:center; gap:8px; }
  .dot { width:10px; height:10px; border-radius:50%; }
  .dot.ok { background:#30d158; box-shadow:0 0 8px rgba(48,209,88,.6); }
  .dot.bad { background:#ff453a; }
  .row { display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid #1f1f22; }
  .row:last-child { border:none; }
  .row .k { color:#86868b; font-size:13px; }
  .row .v { font-family:"JetBrains Mono",monospace; font-size:13px; }
  .audit { max-height:280px; overflow-y:auto; margin-top:12px; }
  .audit-row { font-family:"JetBrains Mono",monospace; font-size:12px; padding:6px 8px; border-bottom:1px solid #1a1a1c; display:flex; gap:12px; }
  .audit-row .ts { color:#48484a; min-width:140px; }
  .audit-row .evt { min-width:140px; }
  .audit-row .evt.settled { color:#30d158; }
  .audit-row .evt.failed,.audit-row .evt.denied { color:#ff453a; }
  .audit-row .amt { color:#0a84ff; }
  .balance { display:flex; gap:18px; margin-top:6px; }
  .balance .pill { background:#1a1a1c; padding:6px 12px; border-radius:8px; font-family:"JetBrains Mono",monospace; font-size:13px; }
  .balance .pill .label { color:#86868b; margin-right:8px; }
  footer { text-align:center; color:#48484a; margin-top:32px; font-size:12px; }
</style></head><body>
<h1>TWO-AGENT MARKETPLACE</h1>
<div class="grid">
  <div class="card" id="buyer">
    <h2>Loading...</h2>
  </div>
  <div class="card" id="oracle">
    <h2>Loading...</h2>
  </div>
</div>
<footer>Updates every 3 seconds · scrapes /status, /ready, x402_audit.jsonl, on-chain balances</footer>
<script>
async function update() {
  const r = await fetch('/api/state');
  const d = await r.json();
  for (const role of ['buyer', 'oracle']) {
    const a = d[role];
    const ready = a.ready && a.ready.ready;
    const status = a.status && a.status.status || 'down';
    const ticks = a.status && a.status.ticks_completed || 0;
    document.getElementById(role).innerHTML = `
      <h2><span class="dot ${ready?'ok':'bad'}"></span> ${role.toUpperCase()} <span style="margin-left:auto;font-size:12px;color:#86868b">${status}</span></h2>
      <div class="row"><span class="k">Address</span><span class="v">${a.address || '-'}</span></div>
      <div class="row"><span class="k">Ticks</span><span class="v">${ticks}</span></div>
      <div class="row"><span class="k">Ready</span><span class="v">${ready?'yes':'no — '+(a.ready.reason||'')}</span></div>
      <div class="balance">
        <span class="pill"><span class="label">ETH</span>${a.eth_balance.toFixed(6)}</span>
        <span class="pill"><span class="label">USDC</span>$${a.usdc_balance.toFixed(4)}</span>
      </div>
      <div class="audit">
        ${a.audit.slice().reverse().map(e => `
          <div class="audit-row">
            <span class="ts">${(e.timestamp||'').substr(11,8)}</span>
            <span class="evt ${e.event||''}">${e.event||''}</span>
            <span class="amt">${e.amount_usd?'$'+e.amount_usd:''}</span>
          </div>
        `).join('') || '<div style="color:#48484a;padding:8px">no audit events yet</div>'}
      </div>
    `;
  }
}
update();
setInterval(update, 3000);
</script>
</body></html>
"""


@app.route("/")
def index():
    return render_template_string(_TEMPLATE)


if __name__ == "__main__":
    print("Dashboard at http://localhost:5000")
    print(f"Reading agents from: {DEMO_DIR}")
    app.run(host="127.0.0.1", port=5000, debug=False)
