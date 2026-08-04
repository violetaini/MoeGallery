# Dependency Security Maintenance

MoeGallery installs exact, hash-verified dependency graphs so a release resolves to the same packages over time.

## Files

- `backend/requirements.in` contains direct runtime dependencies.
- `backend/requirements.lock.txt` contains the complete universal runtime graph and SHA-256 hashes.
- `backend/requirements-test.in` and `backend/requirements-test.lock.txt` add the test graph.
- `backend/requirements.txt` and `backend/requirements-test.txt` are compatibility entry points that still enforce the hashed locks.
- `frontend/package.json` uses exact direct versions; `frontend/package-lock.json` locks the complete npm graph.

Do not edit generated versions or hashes by hand.

## Regenerate Python Locks

Use the pinned `uv 0.12.0` resolver with Python 3.12 as the resolution baseline:

```bash
python3 -m venv .venv-lock
.venv-lock/bin/python -m pip install "uv==0.12.0"
cd backend
../.venv-lock/bin/uv pip compile --universal --python-version 3.12 --generate-hashes --output-file requirements.lock.txt requirements.in
../.venv-lock/bin/uv pip compile --universal --python-version 3.12 --generate-hashes --output-file requirements-test.lock.txt requirements-test.in
```

On Windows, replace `.venv-lock/bin` with `.venv-lock/Scripts`.

## Required Checks

```bash
python -m pip install "pip==26.2" "pip-audit==2.10.1"
python -m pip install --require-hashes -r backend/requirements-test.lock.txt
python -m pip_audit --strict --require-hashes --disable-pip -r backend/requirements.lock.txt
cd frontend
npm ci
npm audit --audit-level=high
npm run build
```

GitHub Actions repeats these audits for dependency changes, every week, and before release. Dependabot checks Python, npm, and GitHub Actions weekly.

## Emergency Upgrades

1. Confirm the affected and fixed versions from the advisory.
2. Apply the smallest compatible upgrade; review major upgrades separately.
3. Regenerate locks and run the complete backend, frontend, audit, and release-package checks.
4. Publish a patch release and verify health, migrations, uploads, and public browsing after deployment.
5. If an immediate upgrade is impossible, record the advisory, mitigation, owner, and expiration date. Never add an unexplained permanent ignore.
