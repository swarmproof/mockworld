# Releasing mockworld

Releases are cut by pushing a version tag; `.github/workflows/release.yml` builds,
smoke-tests, publishes to PyPI (Trusted Publishing), and creates a GitHub release.

## One-time PyPI setup (Trusted Publishing — no stored token)

1. Project name is `mockworld-mcp` (the plain `mockworld` is reserved by another project).
2. On PyPI → the `mockworld-mcp` project → **Publishing** → add a **Trusted Publisher**:
   - Owner: `swarmproof`
   - Repository: `mockworld`
   - Workflow: `release.yml`
   - Environment: `pypi`
3. In the GitHub repo, create an **Environment** named `pypi` (Settings →
   Environments). Optionally add required reviewers to gate publishes.

Until step 2/3 exist, the `pypi-publish` job fails but the GitHub release and
build artifacts still succeed — so a tag is never wasted.

## Cutting a release

```bash
# 1. bump the version in pyproject.toml and add a CHANGELOG.md entry, land on main
# 2. tag and push
git tag v0.1.0
git push origin v0.1.0
```

The workflow then:
- builds the sdist + wheel and installs the wheel into a clean venv, running
  `mockworld list` and `mockworld demo` as a smoke test;
- creates a GitHub release with the artifacts attached;
- publishes to PyPI via OIDC.

## Verifying

```bash
pip install mockworld-mcp==0.2.0
mockworld demo mock:payments   # identical: True
```
