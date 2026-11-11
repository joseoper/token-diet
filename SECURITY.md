# Security Policy

The `token-diet` project takes the security of developer environments seriously. Because this tool inspects repositories, parses Markdown directives, and manages Git hooks (`--fix-hooks`), security and sandbox boundaries are top priorities.

## Supported Versions

Only the latest release line receives active security updates and vulnerability patches.

| Version | Supported          | Notes |
| ------- | ------------------ | ----- |
| 0.3.x   | :white_check_mark: | Current active release line |
| 0.2.x   | :white_check_mark: | Maintained for bug/security fixes (v0.2.3+ contains hardened containment) |
| < 0.2.3 | :x:                | Deprecated. Vulnerable to symlink traversal and DoS vectors |

We strongly recommend all users upgrade to **v0.2.3** or later:
```bash
brew upgrade token-diet
# Or:
pipx upgrade token-diet-cli
```

## Security Invariants

`token-diet` enforces strict security invariants in its codebase:
1. **Zero Runtime Dependencies:** No third-party packages in `src/token_diet/` to prevent supply-chain compromises.
2. **Repository Containment:** File mutations (`--fix-hooks`) are strictly bound within the repository's `.git/` directory. Symlink targets outside the repository boundary are rejected with `PermissionError`.
3. **Atomic File Operations:** All file updates occur via temporary atomic files with strict permissions (`0o700` for hooks) to eliminate Time-of-Check to Time-of-Use (TOCTOU) races.
4. **Denial of Service Limits:** File reads are bounded to 10 MB per file, preventing memory exhaustion attacks from unbounded pipes or infinite streams (e.g., `/dev/zero`).
5. **Terminal Output Sanitization:** All terminal outputs sanitize ANSI escape sequences and control characters (`[\x00-\x08\x0b-\x1f\x7f]`) to prevent terminal spoofing.

## Reporting a Vulnerability

If you discover a security vulnerability within `token-diet`, please **do not open a public issue**. 

Instead, report it responsibly via one of the following methods:

### 1. GitHub Private Vulnerability Reporting (Preferred)
Submit a confidential advisory directly through GitHub:
[Report a Vulnerability](https://github.com/joseoper/token-diet/security/advisories/new)

### 2. Email
Alternatively, contact the maintainer via the secure maintainer channel:
- **Email:** `joseoper@users.noreply.github.com`
- **Subject:** `[SECURITY] Vulnerability Report: token-diet`

### What to Include in Your Report
To help us triage and resolve the issue quickly, please provide:
- A clear description of the vulnerability and its potential impact.
- Step-by-step instructions or a Minimal Reproducible Example (PoC script/repo).
- The operating system and Python version where the issue was reproduced.
- Any proposed remediation or patch, if available.

## Response & Disclosure Process

- **Acknowledgment:** We will acknowledge receipt of your report within **48 hours**.
- **Assessment & Triage:** We will investigate and confirm the impact within **5 business days**.
- **Fix & Advisory:** A patch will be prepared and published alongside a security advisory. We coordinate with reporters on public disclosure dates.
- **Credit:** Security researchers who discover and responsibly report verified vulnerabilities will be credited in the release notes and advisory (unless anonymity is requested).
