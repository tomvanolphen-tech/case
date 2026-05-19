# CLAUDE.md — Project Guidelines

## Git & GitHub Workflow

**Every meaningful unit of work must be committed and pushed to GitHub.** This ensures no progress is ever lost and any change can be reverted cleanly.

### Rules

1. **Commit after every logical change** — after adding a feature, fixing a bug, updating config, or making any non-trivial edit.
2. **Push to GitHub immediately after committing** — run `git push` after every commit so the remote is always up to date.
3. **Write clean, descriptive commit messages** — use the imperative mood, one short summary line (≤72 chars), optionally followed by a blank line and a brief body if needed. Example:
   ```
   Add user authentication via JWT

   Stores token in httpOnly cookie; expiry is 7 days.
   ```
4. **Never batch unrelated changes into one commit** — if two things are logically separate, make two commits.
5. **Stage only relevant files** — prefer `git add <specific-file>` over `git add .` to avoid accidentally committing secrets or build artifacts.

### Typical flow

```
git add <files>
git commit -m "Short imperative description"
git push
```

### Branch strategy

- `main` is always stable and deployable.
- For larger features or experiments, create a branch: `git checkout -b feature/<name>`
- Merge back to `main` via a pull request once the work is complete and tested.

## Repository

- **GitHub:** https://github.com/tomvanolphen-tech/case
- **Remote name:** `origin`
