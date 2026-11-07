# AGENTS.md — Directives for AI Coding Assistants

Welcome, agent. This repository is built around **Token Diet** principles to eliminate silent context bloat. Adhere strictly to these directives:

## Core Directives

1. **Architecture Context:** Before modifying diagnostic logic, refer to [`docs/remediation-playbook.md`](docs/remediation-playbook.md) for containment procedures and [`docs/ci-integration.md`](docs/ci-integration.md) for automated gatekeeper integration.
2. **Zero External Dependencies:** `src/token_diet/` must remain pure Python standard library (`sys`, `os`, `json`, `argparse`, `typing`). Do not introduce third-party runtime dependencies.
3. **Test-Driven Development (TDD):** Every heuristic, threshold badge (`[OK]`, `[WARN]`, `[ALERT]`), or CLI argument change must have tests under `tests/` (discovered by `test_*.py`). Feature modules keep unit tests in a matching `tests/test_<module>.py`; CLI flags and cross-module wiring are covered in `tests/test_token_audit.py`. Verify with:
   ```bash
   python3 -m unittest discover -s tests -p 'test_*.py'
   ```
4. **In-Session Runtime Token Hygiene:** Adhere to [Phase 4 guidelines](docs/remediation-playbook.md#phase-4-in-session-runtime-hygiene-active-execution-guards): prefer line-range reads (`start_line`, `end_line`) and symbol searches over full-file dumping, enforce targeted block replacements over whole-file rewrites, and keep responses concise and free of conversational pleasantries.