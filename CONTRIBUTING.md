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

## Release & Distribution Protocol (All Active Channels)

Whenever a new version of `token-diet` is prepared, it must be published across **all active distribution channels**. Never perform a partial release.

### Target Channels
1. **GitHub Git Repository:** Branch `main` and version tag `vX.Y.Z` on remote `public` (`https://github.com/joseoper/token-diet.git`).
2. **GitHub Releases:** Release `vX.Y.Z` on GitHub containing release notes and binary assets (`dist/token_diet_cli-*.whl` and `dist/token_diet_cli-*.tar.gz`).
3. **Homebrew Tap:** Formula in `joseoper/homebrew-tap` (`Formula/token-diet.rb`) with updated tag archive URL and recalculated SHA-256.
4. **PyPI Build Artifacts:** Rebuilt wheels and sdist packages in `dist/`.

### Automated Release Helper
An automated script is provided in `scripts/release.sh` to execute and validate the complete multi-channel release flow:
```bash
./scripts/release.sh <X.Y.Z>
```

### Manual Step-by-Step Procedure

1. **Verify Quality & Tests:**
   ```bash
   python3 -m unittest discover -s tests -p 'test_*.py'
   ```

2. **Update Version in Packaging Manifest:**
   Update `version = "X.Y.Z"` in `pyproject.toml`.

3. **Build Wheels and Source Distributions:**
   ```bash
   rm -rf dist/ build/ src/*.egg-info
   python3 -m build
   ```

4. **Commit, Tag, and Push to Public Remote:**
   ```bash
   git commit -am "chore(release): vX.Y.Z"
   git tag -a vX.Y.Z -m "Release vX.Y.Z"
   git push public main
   git push public vX.Y.Z
   ```

5. **Create GitHub Release with Assets:**
   ```bash
   gh release create vX.Y.Z dist/token_diet_cli-X.Y.Z* --title "vX.Y.Z" --generate-notes
   ```

6. **Update Homebrew Tap (`joseoper/homebrew-tap`):**
   Compute the tarball SHA-256:
   ```bash
   TAR_URL="https://github.com/joseoper/token-diet/archive/refs/tags/vX.Y.Z.tar.gz"
   SHA=$(curl -sL "$TAR_URL" | shasum -a 256 | awk '{print $1}')
   ```
   Update `Formula/token-diet.rb` with the new URL and SHA-256 checksum, commit, and push:
   ```bash
   git checkout homebrew-tap
   # Update Formula/token-diet.rb
   git commit -am "chore(formula): bump token-diet to vX.Y.Z"
   git push tap homebrew-tap:main
   git checkout main
   ```

7. **Verify All Channels:**
   - Confirm `gh release view vX.Y.Z` lists both release assets.
   - Confirm `brew info joseoper/tap/token-diet` resolves to `vX.Y.Z`.

