# AGENTS.md — Directives for AI Coding Assistants

Welcome, agent. This repository is built around **Token Diet** principles to eliminate silent context bloat. Adhere strictly to these directives:

## Core Directives

1. **Architecture Context:** Before modifying diagnostic logic, refer to [`docs/remediation-playbook.md`](docs/remediation-playbook.md) for containment procedures and [`docs/ci-integration.md`](docs/ci-integration.md) for automated gatekeeper integration.
2. **Zero External Dependencies:** `src/token_diet/` must remain pure Python standard library (`sys`, `os`, `json`, `argparse`, `typing`). Do not introduce third-party runtime dependencies.
3. **Test-Driven Development (TDD):** Every heuristic, threshold badge (`[OK]`, `[WARN]`, `[ALERT]`), or CLI argument change must have tests in `tests/test_token_audit.py`. Verify with:
   ```bash
   python3 -m unittest discover -s tests -p 'test_*.py'
   ```