# Contributing to Token Diet

Thank you for your interest in contributing to **Token Diet**! This guide outlines our development workflow and coding standards.

## Code of Conduct

Please be respectful, constructive, and considerate of all contributors and users.

## Core Engineering Principles

1. **Zero External Dependencies:** The CLI tool strictly utilizes the Python standard library (`sys`, `os`, `json`, `argparse`). Do not introduce third-party runtime dependencies.
2. **Cross-Platform Compatibility:** Code must execute seamlessly across macOS, Linux, and Windows. Use `os.path.expanduser()` and standard path handling.
3. **Test-Driven Development (TDD):** Every bugfix, heuristic change, or new CLI flag must include accompanying automated unit tests.
4. **Conventional Commits:** Write clear commit messages using the Conventional Commits format (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
5. **Security & Privacy:** Strictly zero API keys, secrets, personal emails, or machine-specific absolute paths in code or tests.

## Development Workflow

1. **Fork and Clone:**
   ```bash
   git clone https://github.com/<your-username>/token-diet.git
   cd token-diet
   ```

2. **Create a Topic Branch:**
   ```bash
   git checkout -b feat/your-feature-name
   ```

3. **Run Tests:**
   Verify the full automated test suite before opening a PR:
   ```bash
   python3 -m unittest discover -s tests -p 'test_*.py'
   ```

4. **Submit a Pull Request:**
   - Keep pull requests focused on a single change.
   - Explain the motivation and behavior in the PR description.
   - Ensure GitHub Actions CI workflows pass cleanly.
