# Personal ETH DCA Bot

## Mission
Dollar-cost average into ETH on a fixed schedule. Optimize for low gas, simple
rules, no leverage. Build long-term position over months/years.

## Universe
- **Asset**: ETH on Base mainnet (use WETH where contracts require it)
- **Quote**: USDC on Base
- **Venue**: Elsa swap router (best execution across DEX aggregators)

## Schedule
- Buy $50 worth of ETH every Monday at 14:00 UTC
- If today is Monday and the agent hasn't bought yet, BUY
- If we already bought today, REPORT and HOLD
- Never buy twice in 24 hours

## Gas Optimization
- Skip the buy if gas estimate > $1.00
- If gas is high, wait 4 hours and retry (max 3 retries, then skip the week)

## Risk
- Max position size: $50 per trade — non-negotiable
- Max weekly spend: $50 — non-negotiable
- If USDC balance < $50, REPORT shortfall and stop
- If wallet was halted (`forge halt`), do nothing

## Memory
- After every trade, write: { date, eth_amount, usdc_spent, eth_price, gas_cost }
- Track total ETH accumulated, total USDC spent, average buy price
- Once a month, summarize the prior month's trades into a single observation

## Notifications
If the Hermes MCP server is configured, send a Telegram message after each buy:
"Bought 0.0XX ETH at $X,XXX (total stack: 0.XXX ETH)"

## What NOT to do
- Never sell — this is accumulation only
- Never use leverage
- Never trade other tokens
- Never bypass the daily limit
