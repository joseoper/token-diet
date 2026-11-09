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
5. **Mandatory Full-Spectrum Release Protocol:** When releasing or bumping a version (`vX.Y.Z`), you MUST NOT stop at pushing git tags. You are strictly required to publish across **ALL** active distribution channels where `token-diet` is distributed:
   - **Step A (Test & Package):** Verify tests pass (`python3 -m unittest discover -s tests -p 'test_*.py'`), ensure version is updated in `pyproject.toml`, and build distribution assets via `python3 -m build` (generates `.whl` and `.tar.gz` in `dist/`).
   - **Step B (Git Tag & Remote):** Commit version bump, create annotated tag `vX.Y.Z`, and push both branch and tag to the public remote (`git push public main && git push public vX.Y.Z`).
   - **Step C (GitHub Release & Assets):** Create the official release via `gh release create vX.Y.Z dist/token_diet_cli-X.Y.Z* --title "vX.Y.Z" --generate-notes`. Never leave releases empty or missing wheel/sdist assets.
   - **Step D (Homebrew Tap):** Update `Formula/token-diet.rb` with the new tarball URL (`https://github.com/joseoper/token-diet/archive/refs/tags/vX.Y.Z.tar.gz`) and the recalculated SHA-256 (`curl -sL <url> | shasum -a 256`). Commit and push to `joseoper/homebrew-tap` (`git push tap homebrew-tap:main`).
   - **Step E (Verification):** Verify that both GitHub Releases (`gh release list`) and Homebrew formula report the latest version. A release is only complete when all channels are verified. Script helper: `scripts/release.sh <version>`.