# GitHub publication preparation

## Repository details

- **Suggested name:** `researchforge-ai`
- **Short description:** Local-first Agentic AI research assistant with document RAG, LangGraph workflows, evidence checks, citations, and safe abstention.
- **Topics:** `generative-ai`, `rag`, `agentic-ai`, `langgraph`, `ollama`, `qdrant`, `fastapi`, `nextjs`, `postgresql`, `local-first`
- **License:** MIT, as present in the repository's `LICENSE` file.
- **Copyright line:** `Copyright (c) 2026 shashank s`
- **Authenticated owner:** `shashanks672` (confirmed through the connected GitHub account; not inferred from the copyright name).
- **Intended URL:** `https://github.com/shashanks672/researchforge-ai`
- **Intended branch:** `main`
- **First commit message:** `feat: initial ResearchForge AI portfolio release`
- **GitHub availability check:** The connected account listed repositories for `shashanks672`; no repository named `researchforge-ai` was present in the returned pages on 2026-10-27. Recheck immediately before creation.

The MIT license applies to this project's original code and documentation. It does not
relicense third-party dependencies or future research results retrieved from Wikipedia.
The live adapter preserves source title and link; users remain responsible for applicable
source terms when they use it. The old Wikipedia passage has been replaced in bundled tests
with original, explicitly synthetic text and a reserved `.invalid` URL. The historical
acceptance report remains an account of the earlier run, not a test fixture or a claim of
current live acceptance. See [fixture provenance](../evaluation/ATTRIBUTION.md).

No dependency source archives are vendored in the repository. `uv.lock` and
`package-lock.json` identify packages but do not include their source. Anyone distributing
installed or bundled dependencies must follow each package's license terms.

## Safe initial commit allowlist

The repository currently has no initial commit or remote, so nothing is staged. The exact
212-path allowlist is recorded in
[`GITHUB_PUBLICATION_ALLOWLIST.txt`](GITHUB_PUBLICATION_ALLOWLIST.txt). The grouped
categories below explain that manifest:

- Root: `.editorconfig`, `.env.example`, `.gitignore`, `.nvmrc`, `.python-version`,
  `IMPLEMENTATION_LOG.md`, `LICENSE`, `README.md`, and `docker-compose.yml`.
- `.github/workflows/` and `.vscode/` project configuration.
- `backend/alembic.ini`, `backend/app/`, `backend/migrations/`, `backend/tests/`,
  `backend/pyproject.toml`, and `backend/uv.lock`. The checked-in PDF is a two-page
  synthetic Juniper document created for testing.
- `frontend/.env.example`, frontend configuration and lockfiles, `frontend/src/`,
  `frontend/tests/`, and `frontend/e2e/`.
- `scripts/` local bootstrap, start/stop, test, and evaluation utilities.
- `docs/` Markdown documentation and these 11 current Phase 8A screenshots:
  `phase-8a-citation-mobile.png`, `phase-8a-evidence-review-desktop.png`,
  `phase-8a-existing-local-run-desktop.png`, `phase-8a-history-desktop.png`,
  `phase-8a-home-desktop.png`, `phase-8a-home-mobile.png`,
  `phase-8a-library-desktop.png`, `phase-8a-library-mobile.png`,
  `phase-8a-result-desktop.png`, `phase-8a-result-mobile.png`, and
  `phase-8a-settings-desktop.png`. They contain synthetic UI examples or the saved local
  Juniper demo.
- `evaluation/` synthetic datasets, provisional results, annotation guidelines, README,
  and attribution/provenance note. These are not human-reviewed quality benchmarks.

This allowlist excludes:

- `.env`, all `.env.local` files, `.local/` (including the Wikimedia contact), `data/`,
  uploaded documents, local databases, logs, model and embedding caches, and generated
  `frontend/test-results/` output.
- `docs/screenshots/phase-0-*.png` through `phase-4-*.png` due to personal identifiers.
- `docs/screenshots/phase-8a/baseline-home-desktop.png` and
  `docs/screenshots/phase-8a/baseline-home-mobile.png` due to personal identity and private
  document/history content.
- All other files under `docs/screenshots/phase-8a/` are limited to the 11 named captures
  above; do not stage the two excluded baseline images.
- Build outputs, `node_modules/`, virtual environments, caches, and temporary files.

Before staging, inspect the literal candidate list and the staged diff. A pattern scan of
the 189 included text files found no private home paths or private-key blocks. Its
credential-word matches were limited to local-only database password examples, CI test
configuration, environment-backed application settings, and scripts that read credentials
from local configuration. Email-like strings are limited to test fixtures; their values
were not included in the report. A pattern scan is not a guarantee, so review new or
changed files manually and never add private configuration or user research records.

## Planned Stage B commands

```text
feat: initial ResearchForge AI portfolio release
```

After the separate explicit authorization, review the manifest, then stage only its paths:

```bash
git add --pathspec-from-file=docs/GITHUB_PUBLICATION_ALLOWLIST.txt
git diff --cached --name-status
git diff --cached
git commit -m "feat: initial ResearchForge AI portfolio release"
```

Then create the public repository, configure `origin`, and push the reviewed `main`
branch as separate operations:

```bash
gh repo create shashanks672/researchforge-ai --public --description "Local-first AI research assistant with document RAG, citations, and evidence-based abstention"
git remote add origin https://github.com/shashanks672/researchforge-ai.git
git push -u origin main
```

These are proposals only; none were run during Stage A. The current local environment has
no `gh` executable, so install/configure GitHub CLI and authenticate locally with
`gh auth login --web`, or use another authenticated Git transport. The connected GitHub
account used to verify the intended owner does not establish local Git push authentication.

## Publishing steps

1. Confirm the public visibility choice and the exact copyright line in `LICENSE`.
2. Install GitHub CLI and authenticate locally if using it: `gh auth login --web`.
3. Recheck that `researchforge-ai` is still available under `shashanks672`.
4. Stage only the paths listed in `docs/GITHUB_PUBLICATION_ALLOWLIST.txt` with
   `git add --pathspec-from-file=docs/GITHUB_PUBLICATION_ALLOWLIST.txt`.
5. Review `git diff --cached --name-status` and the full staged diff before committing.
6. Create the public repository, then configure `origin` for
   `https://github.com/shashanks672/researchforge-ai.git`.
7. Push the reviewed `main` branch only under the same explicit authorization.

No repository, commit, remote, or push was created as part of this preparation.
