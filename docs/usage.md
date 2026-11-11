# Token Diet — CLI Usage & Command Reference

`token-diet` is a zero-dependency CLI that audits static prompt overhead, detects hidden execution hooks, and enforces context budgets across your repositories and workstation.

---

## 1. Quick Start

### Installation & Environment Requirements

`token-diet` requires **Python >= 3.10** and operates with zero runtime dependencies (pure standard library: `sys`, `os`, `json`, `argparse`, `typing`).

```bash
# Recommended: Isolated installation via pipx
pipx install token-diet-cli

# Via Homebrew (macOS & Linux):
brew install joseoper/tap/token-diet

# Via standard pip:
pip install token-diet-cli
```

### Basic Execution

Run `token-diet` from the root of any repository to audit active agent directives and pre-commit hooks:

```bash
token-diet
```

Sample output:
```text
================================================================================
TOKEN DIET: FOOTPRINT & CONTEXT AUDIT
================================================================================
File / Directive                               |     Bytes |    Tokens |   Status
--------------------------------------------------------------------------------
AGENTS.md                                      |     2,450 |       612 |     [OK]
.cursorrules                                   |    18,240 |     4,560 |  [ALERT]
================================================================================
Total Bytes:     20,690 B
Total Tokens:    ~5,172 estimated base tokens per turn
Files Detected:  2 of 2

⚠️  HIGH CONTEXT FOOTPRINT DETECTED:
  Files marked [ALERT] exceed 16 KB (>4k tokens), increasing cache-miss exposure and context footprint.
  Recommendation: Decouple procedures into On-Demand Skills using the LUT Router pattern.
```

---

## 2. Status Indicators & Heuristic Thresholds

`token-diet` evaluates files against heuristic byte thresholds designed to balance instruction completeness with context efficiency.

> [!NOTE]
> **Heuristics vs. Provider Limits:** The `[OK]`, `[WARN]`, and `[ALERT]` thresholds are pragmatic engineering heuristics, **not hard limits mandated by AI model providers**. A file exceeding 16 KB remains completely valid and ingestible by any LLM. These indicators simply serve to alert teams when static instruction files begin to consume significant portions of early turn payloads and increase cache-miss exposure. Teams can override or configure strict limits in CI using `--max-tokens <N>` and `--max-delta <%>`.

| Status Badge | Byte Range | Estimated Tokens | Architectural Meaning & Recommended Action |
|:---:|:---:|:---:|---|
| 🟢 `[OK]` | `< 4 KB` | `< 1,000 tokens` | **Low Footprint:** Lean static directive. Leaves maximum headroom for codebase context while minimizing cache-miss re-ingestion costs. |
| 🟡 `[WARN]` | `4 KB – 16 KB` | `1,000 – 4,000 tokens` | **Moderate Footprint:** Acceptable size, but consider extracting specialized procedures into on-demand skills. |
| 🔴 `[ALERT]` | `> 16 KB` | `> 4,000 tokens` | **High Footprint:** Monolithic rules consume substantial working context and increase cache-miss exposure. Recommended: decouple into On-Demand Skills. |
| 🚨 `[HOOK ALERT]` | — | — | **Hidden Execution Leak:** Active `pre-commit` hook invokes cloud LLMs on every `git commit`. Replace with deterministic linters. |

> **Architectural Recommendation:** Aim to keep root directives (`AGENTS.md`, `CLAUDE.md`, `.cursorrules`) under **~3 KB (< 750 tokens)**, housing detailed runbooks in `skills/<name>/SKILL.md`. This threshold is a rule of thumb for clean architectural routing, not an absolute metric of instruction quality.

---

## 3. Command Reference & CLI Options

### Basic Audit
```bash
# Audit current directory
token-diet

# Audit a specific instruction file
token-diet AGENTS.md

# Audit an entire folder recursively
token-diet docs/
```

### Auto-Remediate Rogue Git Hooks (`--fix-hooks`)
Neutralizes unmonitored AI review commands in `.git/hooks/pre-commit` surgically. Preserves surrounding script logic, creates an atomic `.bak` backup, and keeps executable permissions:

```bash
# Preview changes with a colored unified diff (no files modified):
token-diet --fix-hooks --dry-run

# Interactive remediation (prompts for confirmation [y/N]):
token-diet --fix-hooks

# Non-interactive remediation (ideal for scripts and automated CI):
token-diet --fix-hooks -y
```

### Audit Workstation-Wide Global Directives (`--global`)
Scans standard user-level assistant configurations across your home directory (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.gemini/GEMINI.md`, etc.):

```bash
token-diet --global
```

### Breakdown Footprint per Heading (`--sections`)
Identifies which section of a bloated Markdown directive contributes the most tokens:

```bash
token-diet --sections AGENTS.md
```

Sample output:
```text
SECTION BREAKDOWN: MARKDOWN HEADING FOOTPRINT
================================================================================
AGENTS.md  (23,914 B / ~5,978 tokens)
  Line | Heading                                  |     Bytes |    Tokens |   Status
--------------------------------------------------------------------------------
     1 | Preamble & Behavioral Directives         |     1,240 |       310 |     [OK]
    45 | Database Migration Runbook               |     8,920 |     2,230 |   [WARN]
   210 | Dual-Agent Review & Arbitration Protocol |    13,754 |     3,438 |   [WARN]
================================================================================
```

### Audit Declared MCP Schemas (`--mcp`)
Calculates the injection cost of every active Model Context Protocol (MCP) server declared in `opencode.json`, `.mcp.json`, or `mcp.json`:

```bash
token-diet --mcp
```

### CI/CD Quality Gates & Budget Enforcement

```bash
# Fail build if any file triggers [WARN] or [ALERT]:
token-diet --strict

# Enforce a maximum token ceiling on any single directive:
token-diet --max-tokens 1500

# Compare against a baseline and fail on regressions:
token-diet --baseline .token-diet-baseline.json --max-delta 10

# Generate or update a baseline file:
token-diet --save-baseline .token-diet-baseline.json
```

### Machine-Readable JSON Output (`--json`)
Outputs complete audit diagnostics as structured JSON for automation and dashboards:

```bash
token-diet --json
```

---

## 4. Agentic Self-Remediation Prompt

To have your AI coding assistant (Claude Code, Gemini CLI, Cursor, Windsurf, OpenCode) audit and refactor bloated rules autonomously, paste this prompt:

```text
Run `token-diet` in this repository. If you detect any files marked [ALERT] or [WARN], follow `docs/remediation-playbook.md` to decouple operational procedures into on-demand skills under `skills/<skill-name>/SKILL.md`. Compress the root instruction file to a concise Look-Up Table (LUT Router) targeting under ~3 KB (< 750 tokens). If an irregular hook is flagged, run `token-diet --fix-hooks`. Verify that all tests pass and `token-diet` reports [OK].
```

---

## 5. Next Steps

- **[Remediation Playbook](remediation-playbook.md):** Step-by-step guide to implement the Look-Up Table (LUT) Router pattern.
- **[CI/CD Integration Guide](ci-integration.md):** GitHub Actions workflows and pre-commit hook setups.
- **[Technical Architecture](architecture.md):** Module breakdown, hook isolation, and static analysis design.
