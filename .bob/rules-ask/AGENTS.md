# Project Documentation Context (Non-Obvious Only)

- The repo root (`main` / `feature/member3-ai` / `feature/member1-vscode` branches) contains only a `.gitignore` — all actual source code is on `feature/member1-backend-core-intelligence`.
- The project is a monorepo stub: the only real package is `apps/api/` (NestJS). No root-level workspace config exists yet.
- Linting is done with `oxlint`, not ESLint — oxlint config is in `apps/api/.oxlintrc.json`. ESLint-specific advice does not apply.
- Prettier config is minimal (`apps/api/.prettierrc`): single quotes + trailing commas only. Everything else is Prettier default.
