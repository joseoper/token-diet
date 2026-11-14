# Token Diet — Technical Architecture & Internal Design

`token-diet` is engineered as a deterministic, zero-dependency static linter for AI coding environments. It operates directly on the local filesystem **before** tokens are loaded, serialized, or billed by model providers.

---

## 1. Design Philosophy

| Principle | Technical Implementation |
|---|---|
| **Zero Runtime LLM Overhead** | Pure Python standard library (Python >= 3.10). No external pip packages, network calls, or small-model inference passes; every audit is a deterministic offline pass over local files. |
| **Architectural Causality** | Operates at the source of context pollution (the filesystem) rather than reacting to outgoing HTTP streams after tokens have already been billed. |
| **Safe & Reversible Remediation** | `--fix-hooks` employs atomic backups (`.bak`), file modification checks, and executable bit preservation. It disables offending commands without corrupting developer pipelines. |
| **Deterministic Quality Gates** | Predictable exit codes (`0` for success, `1` for violations) enable seamless enforcement in GitHub Actions and pre-commit hooks. |

---

## 2. Module Breakdown

```
src/token_diet/
├── __init__.py      # Package metadata, version exports
├── __main__.py      # python -m token_diet entrypoint
├── cli.py           # Primary argument parser, orchestrator, and terminal renderer
├── git_hooks.py     # Git hooks resolution, worktree traversal, and surgical remediation
├── mcp_audit.py     # MCP configuration discovery and schema token accounting
├── metrics.py       # Centralized token heuristics, thresholds, and formatting utilities
├── baseline.py      # Baseline tracking, regression delta calculations, and budget checks
└── sections.py      # Prefix-matched Markdown heading breakdown and byte attribution
```

### `cli.py` — Orchestrator & CLI Interface
Handles CLI option parsing (`argparse`), path resolution, status determination (`[OK]`, `[WARN]`, `[ALERT]`), and terminal rendering. Implements exit-code semantics for CI pipelines (`--strict`, `--max-tokens`).

### `git_hooks.py` — Hook Resolution & Surgical Neutralization
- **Repository Discovery:** Traverses the filesystem to locate active Git directories, properly handling:
  - Standard Git repositories (`.git/hooks/`).
  - Linked Git worktrees (`.git` file referencing `gitdir`).
  - Git submodules.
  - Repositories configuring custom hook locations via `core.hooksPath`.
- **Command Isolation:** Scans `.git/hooks/pre-commit` for known AI/LLM review commands (`gga`, `opencode`, `gentle-ai`, `claude`, `gemini`, `ollama`, `codex`, `aider`, `cody`, `llm`, plus the `llm review` phrase) matched at command position: as `argv[0]` (path-qualified binaries included), or after leading `NAME=value` assignments and wrapper commands (`sudo`, `env`, `command`, `exec`, `xargs`, `time`, `nohup`, `nice`). Keywords used as plain arguments (e.g. `grep -r claude docs`) are not invocations.
- **Surgical Neutralization:**
  - Ignores existing comments and respects chained shell operators (`&&`, `||`, `;`, pipes).
  - On compound lines, replaces only the offending subcommand with `true  # [token-diet disabled: <command>]`, ensuring test runners (`npm test`, `pytest`) continue executing.
  - On standalone lines where the entire statement is the AI invocation, comments out the line (`# [token-diet disabled]: <command>`).
  - Creates an atomic `.bak` backup before writing and preserves executable permissions (`chmod +x`).

### `mcp_audit.py` — MCP Configuration & Schema Discovery
- Checks five fixed candidate paths in a single directory (no recursive walk): `opencode.json`, `.mcp.json`, `mcp.json`, `.cursor/mcp.json`, and `.vscode/mcp.json`.
- Extracts declared tool server definitions and serializes schema payloads to measure static token footprint.
- Attributes token counts per server, warning developers when idle tools exceed context budgets.

### `metrics.py` — Token Estimation & Footprint Calibration
- Implements the standard `cl100k_base` / `o200k_base` heuristic (~4 characters/bytes per token for structured prose and Markdown).
- Centralizes pragmatic architectural thresholds (heuristics designed to protect context windows, rather than provider-imposed constraints):
  - `THRESHOLD_WARN_BYTES = 4,000` (~1,000 tokens)
  - `THRESHOLD_ALERT_BYTES = 16,000` (~4,000 tokens)

### `baseline.py` — Regression Budget Enforcement
- Stores snapshot audits in a portable JSON schema.
- Calculates delta percentages between current files and recorded baselines.
- Enables PR gatekeeping against creeping instruction bloat (`--max-delta <%>`).

### `sections.py` — Markdown Heading Footprint Attribution
- Parses Markdown directives into level-2 (`##`) heading chunks.
- Computes UTF-8 byte counts and token estimates per heading, showing developers exactly which section is driving prompt bloat.

---

## 3. Technical Boundaries & Limitations

To guarantee zero external dependencies and deterministic offline execution, `token-diet` operates with clear, well-defined operational boundaries:

| Dimension | Mechanism | Operational Boundary |
|---|---|---|
| **Token Estimation** | Fast heuristic (~4 bytes per token) | Heuristic estimation without provider-specific tokenizer overhead. Code density (~2.5–3.2 bytes/token) and non-Latin scripts will have slight variance. |
| **MCP Schemas** | Static inspection of local config files | Reports declared schema overhead. Schemas fetched dynamically by servers at runtime via protocol handshakes are not measurable statically. |
| **Git Hooks Remediation** | Command-position token matching (no shell parsing) | `--fix-hooks` neutralizes detected AI commands and creates `.bak` backups. Complex custom bash scripts should be manually verified. |
| **Directive Scope** | Standard file patterns (`AGENTS.md`, `CLAUDE.md`, `.cursorrules`, etc.) | Audits well-known directives. Custom tooling with proprietary naming paths should be passed explicitly as file arguments. |

---

## 4. Test Suite & Quality Assurance

The codebase includes an automated unit test suite with 142 isolated, deterministic test cases covering core modules and CLI workflows:

```bash
# Run the complete test suite
python3 -m unittest discover -s tests -p 'test_*.py'
```

- `tests/test_git_hooks.py`: Verifies command-position hook detection, git directory/hooks-path resolution, and syntax-safe neutralization on compound shell lines.
- `tests/test_token_audit.py`: Tests CLI execution, threshold flags, error handling, and JSON output formatting.
- `tests/test_baseline.py`: Verifies baseline creation, delta calculations, and budget threshold gates.
- `tests/test_mcp_audit.py`: Validates MCP configuration parsing and token schema calculations.
- `tests/test_sections.py`: Tests Markdown heading chunking and attribution logic.
- `tests/test_security.py`: Verifies symlink and path-boundary containment for hook edits, file-size limits, `--max-delta` NaN/Inf rejection, ANSI sanitization, and detection false-positive resistance.

---

## 5. Next Steps

- **[CLI Usage Guide](usage.md):** Complete command options and recipes.
- **[Benchmark Methodology](benchmarks.md):** 20-turn session simulation and memory metrics.
- **[Remediation Playbook](remediation-playbook.md):** Implementation guide for the Look-Up Table (LUT) Router pattern.
