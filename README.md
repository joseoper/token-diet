# token-diet

Audit token footprint and detect silent context leaks in AI agent workflows.

Zero-dependency CLI for **Claude Code**, **Cursor**, **Codex**, **Gemini**, and **OpenCode**.

---

## Why?

AI coding assistants inject instruction files (`AGENTS.md`, `CLAUDE.md`, `.cursorrules`) into the system prompt on **every single turn**. A bloated 25 KB prompt file forces the model to re-process ~6,000 tokens on every message, draining rate limits and breaking prompt cache discounts.

Worse, some local tools install hidden `pre-commit` hooks that send your entire git diff to an LLM on every commit.

`token-diet` scans your repository or workstation in milliseconds to:
- **Audit prompt size:** Flags instruction files that exceed context budgets (`[OK]`, `[WARN]`, `[ALERT]`).
- **Catch rogue git hooks:** Detects and disables silent LLM review hooks in `.git/hooks/pre-commit` (`--fix-hooks`).
- **Guard CI pipelines:** Fails PR builds if prompt expansions exceed token thresholds (`--strict`, `--max-tokens`).
- **Zero dependencies:** Pure Python standard library (Python >= 3.8). Runs in < 10ms.

---

## Installation

### Via Homebrew (macOS & Linux)
```bash
brew install josephrotts/tap/token-diet
# Or:
brew tap josephrotts/tap
brew install token-diet
```

### Via `pipx` (Recommended for Isolated CLI)
```bash
# Install directly from GitHub:
pipx install git+https://github.com/josephrotts/token-diet.git

# Or install locally in editable mode:
pipx install -e .
```

### Via `pip` / `uv`
```bash
# Using pip:
pip install .

# Using uv:
uv tool install git+https://github.com/josephrotts/token-diet.git
```

### Running Directly from Source (No Installation Needed)
```bash
git clone https://github.com/josephrotts/token-diet.git
cd token-diet
PYTHONPATH=src python3 -m token_diet
```

---

## Usage

### 1. Instant Health Check in Current Directory
Simply run `token-diet` in any project repository. It automatically scans local directives and checks for dangerous pre-commit hooks:

```bash
token-diet
```

**Example Output:**
```text
================================================================================
TOKEN DIET: FOOTPRINT & CONTEXT AUDIT
================================================================================
File / Directive                               |     Bytes |    Tokens |   Status
--------------------------------------------------------------------------------
/Users/developer/my-project/AGENTS.md          |       962 |       240 |     [OK]
/Users/developer/my-project/.cursorrules       |     1,240 |       310 |     [OK]
================================================================================
Total Bytes:     2,202 B
Total Tokens:    ~550 estimated base tokens per turn
Files Detected:  2 of 2
```

### 2. Automated Alerts: Context Bloat & Invisible Pre-Commit Hooks
When a prompt file is oversized or a git hook silently burns tokens on every commit, `token-diet` issues an instant visual alert:

```bash
token-diet
```

**Example Alert Output:**
```text
================================================================================
TOKEN DIET: FOOTPRINT & CONTEXT AUDIT
================================================================================
File / Directive                               |     Bytes |    Tokens |   Status
--------------------------------------------------------------------------------
/Users/developer/my-project/AGENTS.md          |    24,500 |     6,125 |  [ALERT]
================================================================================
Total Bytes:     24,500 B
Total Tokens:    ~6,125 estimated base tokens per turn
Files Detected:  1 of 1

🚨 IRREGULAR HOOK DETECTED:
  • [pre-commit] Pre-commit hook invokes AI/LLM review tooling (gga, opencode). This causes invisible token consumption on every commit.
    Path: /Users/developer/my-project/.git/hooks/pre-commit
  💡 Tip: Run 'token-diet --fix-hooks' to automatically neutralize silent AI invocations.

⚠️  CONTEXT BLOAT DETECTED:
  Files marked [ALERT] exceed 16 KB (>4k tokens) and severely penalize context windows.
  Recommendation: Decouple procedures into On-Demand Skills using the LUT Router pattern.
```

### 3. Auto-Fix Silent Pre-Commit Hooks (`--fix-hooks`)
Neutralize unmonitored AI review tooling in `.git/hooks/pre-commit` in a single command with an automatic backup (`.git/hooks/pre-commit.bak`):

```bash
token-diet --fix-hooks
```

**Example Output:**
```text
🛠️  AUTO-REMEDIATION: PRE-COMMIT HOOKS NEUTRALIZED
  • Backup saved: /Users/developer/my-project/.git/hooks/pre-commit.bak
  • Neutralized 1 AI review invocation(s).
  • Safe pre-commit hook is active without silent token bleed.
```

### 4. Audit System-Wide Global Prompts (`--global`)
Scan default assistant instruction files across your entire workstation (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.gemini/GEMINI.md`, etc.):

```bash
token-diet --global
```

### 5. Audit Specific Paths or Folders
```bash
# Audit a single file
token-diet AGENTS.md

# Audit entire directories recursively
token-diet docs/
```

### 6. Automated CI / Pre-Commit Gate
Integrate into your CI pipeline or Git pre-commit workflow to prevent prompt regressions:

```bash
# Fail CI if prompt footprint exceeds 2,500 tokens:
token-diet --max-tokens 2500 AGENTS.md

# Fail CI if any file triggers a [WARN] or [ALERT]:
token-diet --strict docs/
```

### 7. Structured Telemetry Output (`--json`)
Emit structured JSON for automated pipelines, threshold assertions, or telemetry dashboards:

```bash
token-diet --json
```

---

## Health Status Indicators

| Indicator | Byte Threshold | Estimated Tokens | What it Means & Recommended Action |
|---|:---:|:---:|---|
| 🟢 `[OK]` | `< 4 KB` | `< 1,000 tokens` | **Optimal Context:** Fits cleanly within prompt cache. Preserves fast, cheap inference. |
| 🟡 `[WARN]` | `4 KB – 16 KB` | `1,000 – 4,000 tokens` | **Moderate Size:** Acceptable, but review for duplicate instructions or unneeded verbosity. |
| 🔴 `[ALERT]` | `> 16 KB` | `> 4,000 tokens` | **Severe Prompt Bloat:** Monolithic rules degrade reasoning and waste context budget every turn. Decouple into On-Demand Skills. |
| 🚨 `[HOOK ALERT]` | — | — | **Hidden Token Bleed:** Local `.git/hooks/pre-commit` sends code to cloud LLMs on every `git commit`. Replace with static linters. |

---

## What To Do When a Leak is Detected (Action Paths)

When `token-diet` flags an irregularity, follow the corresponding action path (detailed runbooks available in the [Remediation Playbook](docs/remediation-playbook.md)):

### Path A: When an Irregular Git Hook is Flagged (`🚨 IRREGULAR HOOK DETECTED`)
* **Problem:** A local hook inside `.git/hooks/pre-commit` secretly sends git diffs to cloud AI tools on every single commit.
* **Action Path:**
  1. Inspect the script: `cat .git/hooks/pre-commit`
  2. Remove or comment out the automated AI review invocation.
  3. Replace it with fast, local deterministic linters (`ruff`, `eslint`, `biome`).
  4. Relocate semantic AI reviews to **Pull Request gates in CI** (see [CI/CD Integration](docs/ci-integration.md)), where reviews are metered and visible.

### Path B: When an Agent Directive is Bloated (`🔴 [ALERT]`)
* **Problem:** A root instruction file (`AGENTS.md`, `CLAUDE.md`, `.cursorrules`) exceeds 16 KB (> 4,000 tokens), exhausting your token budget on every turn and destroying cache discounts.
* **Action Path (The Look-Up Table / LUT Router Pattern):**
  1. **Extract Specialized Protocols:** Move detailed procedure manuals, test specifications, and review arbitrations into standalone on-demand skills (e.g., `skills/<skill-name>/SKILL.md`).
  2. **Compress Root Directive:** Keep only core behavioral invariants and a routing index in the root file (< 3 KB / < 750 tokens):
     ```markdown
     ## On-Demand Skills
     - When running database migrations, read `skills/db-migrate/SKILL.md`.
     - When preparing a release, read `skills/oss-publisher/SKILL.md`.
     ```
  3. Re-run `token-diet` to confirm the status turns 🟢 `[OK]`.

### Path C: When CI Fails on Token Budget Exceeded (`exit code 1`)
* **Problem:** A Pull Request introduced unbudgeted prompt expansion that violated `--max-tokens <N>` or `--strict`.
* **Action Path:**
  1. Run `token-diet --json` to get the machine-readable breakdown of offending files.
  2. Prune duplicate rules or extract text into skills.
  3. Re-run local check before pushing: `token-diet --strict`.

### Agentic Remediation: Prompt for AI Assistants
To have your AI coding assistant (Claude Code, Gemini CLI, Cursor, Windsurf, OpenCode) remediate prompt bloat autonomously without manual edits, copy and paste this prompt:

```text
Run `token-diet` in this repository. If you detect any files marked [ALERT] or [WARN], follow `docs/remediation-playbook.md` to decouple operational procedures into on-demand skills under `skills/<skill-name>/SKILL.md`. Compress the root instruction file to a concise Look-Up Table (LUT Router) under 3 KB (< 750 tokens). If an irregular hook is flagged, run `token-diet --fix-hooks`. Verify that all tests pass and `token-diet` reports [OK].
```

---

## Running Tests

Token Diet includes an automated test suite with deterministic coverage:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

---

## Repository Structure

```
token-diet/
├── .github/
│   └── workflows/
│       └── ci.yml             # Automated multi-version CI test runner
├── docs/
│   ├── remediation-playbook.md # Step-by-step token containment and LUT routing
│   └── ci-integration.md       # CI workflows & pre-commit gatekeeper examples
├── src/
│   └── token_diet/            # Core Python package (Zero external dependencies)
│       ├── __init__.py
│       ├── __main__.py
│       └── cli.py             # CLI implementation and footprint engine
├── tests/
│   └── test_token_audit.py    # Automated unit test suite (TDD)
├── .gitignore
├── AGENTS.md                  # Agent-friendly repository directives
├── CONTRIBUTING.md            # Contribution guidelines & engineering principles
├── LICENSE                    # MIT Open Source License
├── pyproject.toml             # PEP 621 packaging and CLI entrypoint
└── README.md                  # Project overview and documentation
```

---

## Core Methodology: The 5 Vectors of Token Leakage

Token Diet is built on empirical analysis of how developer environments silently deplete API quotas:

1. **Global Prompt Bloat:** Monolithic instruction files (`CLAUDE.md`, `AGENTS.md`) exceeding 20 KB inject tens of thousands of static tokens on every turn. *Solution: Keep root directives under 3 KB (<750 tokens) and route to on-demand skills.*
2. **Invisible Git Hooks:** Pre-commit hooks that intercept local commits to invoke cloud LLM reviews drain quotas without developer consent. *Solution: Keep local commits deterministic; reserve AI reviews for PR gates.*
3. **Reasoning Effort Inflation:** Running frontier models at `high` reasoning effort for simple syntax or diagnostic queries generates thousands of hidden chain-of-thought tokens. *Solution: Default to `medium` or `low`.*
4. **Static MCP Schemas:** Registering dozens of MCP tools serializes massive JSON parameter schemas into system prompts. *Solution: Prune unused tool servers and enforce lazy-loading.*
5. **Prompt Cache Invalidation:** Injecting dynamic timestamps or changing session IDs at the start of instructions destroys provider prompt caching discounts (up to 90%). *Solution: Maintain immutable instruction prefixes.*

---

## Platform Compatibility

Token Diet is OS-agnostic and cross-platform:
- **CLI Diagnostic Tool:** Pure Python standard library with zero third-party dependencies. Runs seamlessly on **macOS**, **Linux**, and **Windows** (Python >= 3.8).
- **Universal Methodology:** Core principles apply across all assistants (Claude Code, Gemini CLI, OpenAI Codex, OpenCode, Cursor, Windsurf).

---

## Documentation & Guides

For in-depth operational procedures and automated pipeline setups:
- **[Remediation Playbook](docs/remediation-playbook.md):** Step-by-step runbook to prune prompt files, configure reasoning effort, and contain background services.
- **[CI/CD Integration](docs/ci-integration.md):** GitHub Actions workflows and pre-commit configurations for automated token budget enforcement.
- **[Agent Directives (AGENTS.md)](AGENTS.md):** Operational guidelines for AI coding assistants working on this codebase.
- **[Contributing Guidelines](CONTRIBUTING.md):** How to run tests, submit pull requests, and coding standards.

---

## License

This project is licensed under the terms of the [MIT License](LICENSE).
