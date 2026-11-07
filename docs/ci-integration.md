# CI/CD Integration & Automated Quality Gates

Integrating `token-diet` into continuous integration (CI) and pre-commit workflows ensures that prompt directives, rule files, and system configurations do not regress into bloated context hogs over time.

---

## 1. GitHub Actions Workflow

Add `.github/workflows/token-budget-gate.yml` to your repository:

```yaml
name: Token Budget Gate

on:
  pull_request:
    branches: [ main, master ]
    paths:
      - 'AGENTS.md'
      - 'CLAUDE.md'
      - 'GEMINI.md'
      - '.cursorrules'
      - '.cursor/rules/**'
      - 'docs/**'

jobs:
  token-audit:
    name: Enforce Prompt Budget
    runs-on: ubuntu-latest

    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install Token Diet
        run: |
          pip install token-diet

      - name: Run Token Footprint Audit
        run: |
          # 1. Inspect repository directives
          token-diet

      - name: Assert Token Threshold Gate
        run: |
          # Fails the PR build if any rule file exceeds strict thresholds or total tokens exceed 2,500
          token-diet --max-tokens 2500 --strict
```

---

## 2. Local Git Pre-Commit Hook Integration

You can add a fast, deterministic local gate using the [pre-commit](https://pre-commit.com) framework.

Add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: token-diet-check
        name: Token Diet Prompt Gate
        entry: token-diet --strict
        language: system
        files: ^(AGENTS\.md|CLAUDE\.md|GEMINI\.md|\.cursorrules|\.cursor/rules/.*)$
        pass_filenames: false
```

*Because `token-diet` is pure Python standard library and evaluates in < 5ms, it adds zero noticeable latency to local commits while preventing oversized rule injections.*

---

## 3. Pull Request Comment Automation (JSON Telemetry)

Generate structured telemetry reports inside PR reviews using the `--json` flag:

```yaml
      - name: Generate JSON Telemetry
        id: token_audit
        run: |
          token-diet --json > token-footprint.json
          TOTAL_TOKENS=$(jq '.summary.total_tokens' token-footprint.json)
          TOTAL_BYTES=$(jq '.summary.total_bytes' token-footprint.json)
          STATUS=$(jq -r '.summary.status' token-footprint.json)

          echo "total_tokens=$TOTAL_TOKENS" >> $GITHUB_OUTPUT
          echo "total_bytes=$TOTAL_BYTES" >> $GITHUB_OUTPUT
          echo "status=$STATUS" >> $GITHUB_OUTPUT

      - name: Post PR Summary
        uses: actions/github-script@v7
        with:
          script: |
            const tokens = '${{ steps.token_audit.outputs.total_tokens }}';
            const bytes = '${{ steps.token_audit.outputs.total_bytes }}';
            const status = '${{ steps.token_audit.outputs.status }}';
            const body = `### 🥗 Token Diet Quality Gate: **${status}**\n- **Base Injected Tokens:** ~${tokens}\n- **Total Payload:** ${bytes} Bytes`;
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: body
            });
```

---

## 4. Best Practices for Gate Thresholds

| Scope | Recommended Max Threshold | Rationale |
|---|:---:|---|
| **Root Directives (`AGENTS.md`)** | `1,000 tokens` (< 4 KB) | Leaves 99%+ of the context window free for source code and tools. |
| **Project Documentation Folder (`docs/`)** | `5,000 tokens` (< 20 KB) | Prevents documentation trees from exceeding default retrieval limits. |
| **Total Turn Ingestion Budget** | `2,500 tokens` (< 10 KB) | Preserves maximum prompt cache hit rate and minimizes per-turn toll. |

---

## 5. Baseline Regression Budget (PR Delta Gate)

Fixed thresholds miss slow, incremental growth: a directive can double in size over twenty pull requests and never trip `--max-tokens`. A baseline delta gate fails only the growth introduced by the pull request under review.

Commit the baseline on your default branch, then gate every pull request against it:

```yaml
      - name: Checkout Base Branch Baseline
        uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.base.sha }}
          path: base

      - name: Run Baseline Gate
        run: |
          pip install token-diet-cli
          ( cd base && token-diet --json > ../token-baseline.json )
          token-diet --baseline token-baseline.json --max-delta 5
```

`--max-delta 5` allows up to 5% total growth and exits `1` beyond that. A decrease, an unchanged total, or growth exactly at the budget passes, so the gate never fails on noise.

Keep the baseline inside the repository when the base branch is not available at build time:

```bash
token-diet --json > token-baseline.json       # refresh intentionally, on the default branch
token-diet --baseline token-baseline.json --max-delta 5
```

`--baseline` accepts a full `--json` report or a minimal `{"total_tokens": N}` snapshot, so a small committed file is enough.
