# Releasing Letterboxd CLI

Do not publish, push a public repository, or upload to PyPI without explicit maintainer approval.

## 0. Prereqs

- Clean working tree on the release branch.
- Python 3.11+ installed.
- `make ci` passes locally.
- GitHub Actions CI is green for the commit being released.
- README examples have been spot-checked against current Letterboxd behavior.
- GitHub repository: `https://github.com/jamespheffernan/letterboxd-cli`.

## 1. Verify Locally

```bash
make ci
```

This runs lint, tests, compile checks, generated docs checks, package build, and wheel smoke install.

## 2. Update Release Notes

- Update `CHANGELOG.md`.
- Confirm `docs/RELEASE_CHECKLIST.md` reflects the current release state.

## 3. Commit and Tag

```bash
git status --short
git add .
git commit -m "release: prepare v0.1.0"
git tag -a v0.1.0 -m "Release 0.1.0"
```

Only push after approval:

```bash
gh repo create jamespheffernan/letterboxd-cli --public --source . --remote origin
git push origin main --tags
```

## 4. GitHub Release

Create a GitHub release from the tag and mirror the relevant `CHANGELOG.md` section.

## 5. PyPI

PyPI publication is deferred for v0.1.0. If later approved:

```bash
python3 -m pip install build twine
python3 -m build
python3 -m twine check dist/*
python3 -m twine upload dist/*
```

Prefer TestPyPI first if the package name or metadata has not been validated.
