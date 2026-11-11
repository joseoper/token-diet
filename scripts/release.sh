#!/usr/bin/env bash
# ==============================================================================
# scripts/release.sh — Automated Full-Spectrum Release & Distribution for Token Diet
#
# Publishes a new version across all active distribution channels:
# 1. Tests & Quality Gate
# 2. Package Build (wheels + sdist in dist/)
# 3. Git commit, tag, and push to public remote
# 4. GitHub Release with generated notes and binary assets
# 5. Homebrew Tap Formula update (joseoper/homebrew-tap) and push
# ==============================================================================

set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <version>"
  echo "Example: $0 0.2.4"
  exit 1
fi

VERSION="${1#v}"
TAG="v${VERSION}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$REPO_DIR"

echo "======================================================================"
echo " Starting Full-Spectrum Release for Token Diet: ${TAG}"
echo "======================================================================"

# Public release identity (protects private developer emails)
export GIT_AUTHOR_NAME="${GIT_AUTHOR_NAME:-joseoper}"
export GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-joseoper@users.noreply.github.com}"
export GIT_COMMITTER_NAME="${GIT_COMMITTER_NAME:-joseoper}"
export GIT_COMMITTER_EMAIL="${GIT_COMMITTER_EMAIL:-joseoper@users.noreply.github.com}"

# 1. Verify working directory is clean
if [ -n "$(git status --porcelain)" ]; then
  echo "Error: Working directory has uncommitted changes. Please commit or stash first."
  git status -s
  exit 1
fi

# 2. Run automated test suite
echo "[1/6] Running automated test suite..."
python3 -m unittest discover -s tests -p 'test_*.py'

# 3. Update pyproject.toml version
echo "[2/6] Updating version in pyproject.toml to ${VERSION}..."
sed -i '' -E "s/^version = \".*\"/version = \"${VERSION}\"/" pyproject.toml

# 4. Clean and build distribution packages
echo "[3/6] Building distribution packages (wheel + sdist)..."
rm -rf dist/ build/ src/*.egg-info
if command -v uv >/dev/null 2>&1; then
  uv build
elif python3 -m build --help >/dev/null 2>&1; then
  python3 -m build
else
  pipx run build
fi

# 5. Commit and tag release
echo "[4/6] Creating git release commit and tag ${TAG}..."
git add pyproject.toml
git commit -m "chore(release): ${TAG}"
git tag -a "${TAG}" -m "Release ${TAG}"

echo "Pushing main and tag to public remote..."
git push public main
git push public "${TAG}"

# 6. Create GitHub Release with binary assets
echo "[5/6] Creating GitHub Release with attached assets..."
gh release create "${TAG}" dist/token_diet_cli-"${VERSION}"* \
  -R joseoper/token-diet \
  --title "${TAG}" \
  --generate-notes

# 7. Update Homebrew Tap Formula
echo "[6/6] Updating Homebrew Tap formula (joseoper/homebrew-tap)..."
TAR_URL="https://github.com/joseoper/token-diet/archive/refs/tags/${TAG}.tar.gz"

echo "Waiting for GitHub archive to be available..."
sleep 3

SHA="$(curl -sL "${TAR_URL}" | shasum -a 256 | awk '{print $1}')"

if [ -z "$SHA" ] || [ ${#SHA} -ne 64 ]; then
  echo "Error: Failed to compute valid SHA256 from ${TAR_URL}"
  exit 1
fi

echo "Archive SHA256: ${SHA}"

# Update Formula/token-diet.rb in current worktree
sed -i '' -E "s|url \".*\"|url \"${TAR_URL}\"|" Formula/token-diet.rb
sed -i '' -E "s|sha256 \".*\"|sha256 \"${SHA}\"|" Formula/token-diet.rb

git add Formula/token-diet.rb
git commit -m "chore(formula): sync local formula to ${TAG}" || true

# Update and push to homebrew-tap branch
git checkout homebrew-tap
sed -i '' -E "s|url \".*\"|url \"${TAR_URL}\"|" Formula/token-diet.rb
sed -i '' -E "s|sha256 \".*\"|sha256 \"${SHA}\"|" Formula/token-diet.rb

git add Formula/token-diet.rb
git commit -m "chore(formula): bump token-diet to ${TAG}"
git push tap homebrew-tap:main
git checkout main

echo "======================================================================"
echo " RELEASE COMPLETE across all active distribution channels:"
echo " - Git tag & branch: pushed to public/main (${TAG})"
echo " - GitHub Release: https://github.com/joseoper/token-diet/releases/tag/${TAG}"
echo " - Release assets: attached .whl and .tar.gz"
echo " - Homebrew Tap: updated in joseoper/homebrew-tap (formula: token-diet)"
echo "======================================================================"
