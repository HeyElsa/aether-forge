---
name: Bug Report
about: Report a bug in Aether Forge
labels: bug
---

**What happened?**
A clear description of the bug.

**What did you expect?**
What should have happened instead?

**To reproduce**
Steps:
1. Generated agent with `forge generate-fast --name X --idea Y ...`
2. Ran `forge run . --mode paper ...`
3. Observed ...

**Environment**
- OS:
- Python version (`python --version`):
- Aether Forge version (`pip show aether-forge`):
- Planner: (e.g., `openrouter / claude-sonnet-4`)
- `forge doctor` output (paste below):

```
<paste forge doctor output>
```

**Logs**
Relevant lines from `agent.jsonl` or stderr:

```
<paste logs>
```

**Replay file (optional)**
If the bug shows up during a tick, attach `replays/tick_NNNN.json` or paste the output of:
```
forge replay-show ./replays/tick_NNNN.json
```
