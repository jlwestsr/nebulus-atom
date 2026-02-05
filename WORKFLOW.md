# Project Workflow (Nebulus Standard)

## Branching Strategy

We follow a strict **Gitflow-lite** workflow.

### Permanent Branches (Remote)
- **`main`**: Production-ready code.
- **`develop`**: Integration branch for the next release. **All work merges here.**

### Temporary Branches (Local Only)
**CRITICAL**: These branches exist **ONLY** on your local machine. You generally do **NOT** push them to nebulus-atom unless working on a long-lived collaborative feature.

- **`feat/name`**: New features (models, services, UI).
- **`fix/description`**: Bug fixes.
- **`docs/description`**: Documentation updates.
- **`chore/description`**: Maintenance, config, refactoring.

## Workflow Steps

1.  **Start**: Checkout `develop` and pull latest.
    ```bash
    git checkout develop
    git pull nebulus-atom develop
    ```
2.  **Branch**: Create a specific local branch.
    ```bash
    git checkout -b feat/my-new-feature
    ```
3.  **Work**: Implement changes using **Conventional Commits**.
    ```bash
    git commit -m "feat: add new OpenAI service"
    ```
4.  **Verify**: Run tests/start app to ensure stability.
5.  **Merge**: Switch back to `develop` and merge.
    ```bash
    git checkout develop
    git merge feat/my-new-feature
    ```
6.  **Push**: Push **ONLY** `develop`.
    ```bash
    git push nebulus-atom develop
    ```
7.  **Cleanup**: Delete the local branch.
    ```bash
    git branch -d feat/my-new-feature
    ```

## Feature Documentation
All planned features must be documented in `docs/features/` using the `docs/feature_template.md`.
Refer to these documents for branch names, requirements, and verification plans before starting work.
