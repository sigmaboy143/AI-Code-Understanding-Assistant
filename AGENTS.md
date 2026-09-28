# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Project Layout

This is a monorepo with a NestJS API at `apps/api/`. All commands below must be run from `apps/api/`, not the repo root.

## Commands (run from `apps/api/`)

```bash
npm install
npm run build          # nest build (outputs to dist/)
npm run start:dev      # watch mode dev server (port 3000 or $PORT)
npm run lint           # oxlint --type-aware src/ test/
npm run format         # prettier --write
npm run test           # unit tests (*.spec.ts)
npm run test:e2e       # e2e tests (*.e2e-spec.ts) via test/jest-e2e.json
npm run test:cov       # coverage report
```

**Run a single test file:**
```bash
node --experimental-vm-modules ./node_modules/jest/bin/jest.js src/app.controller.spec.ts
```
`--experimental-vm-modules` is required — the standard `jest` binary will fail without it.

## Code Style

- **Prettier**: single quotes, trailing commas everywhere (`"trailingComma": "all"`)
- **Linter**: `oxlint` (not ESLint). `typescript/no-explicit-any` is **off**; `typescript/no-floating-promises` is **error** — always `void` or `await` async calls at statement level.
- **TypeScript**: `strict: true` but `strictPropertyInitialization: false`. Module system is `nodenext` — use `.js` extensions in relative imports even for `.ts` source files.
- **Decorators**: `emitDecoratorMetadata` and `experimentalDecorators` are enabled (required for NestJS DI).

## Testing

- Unit tests: `*.spec.ts` co-located in `src/` — do **not** put them in a separate `test/` folder.
- E2e tests: `*.e2e-spec.ts` in `test/` only, picked up via `test/jest-e2e.json`.
- Test environment is `node`; path aliases from `tsconfig.json` are auto-mapped via `ts-jest`'s `pathsToModuleNameMapper`.

## NestJS Conventions

- Modules/controllers/services follow standard NestJS decorator pattern.
- `src/main.ts` bootstrap uses `void bootstrap()` (not `.then()`/`catch()`) to satisfy the no-floating-promises rule.
- `strictPropertyInitialization: false` means injected constructor dependencies don't need `!` non-null assertions.
