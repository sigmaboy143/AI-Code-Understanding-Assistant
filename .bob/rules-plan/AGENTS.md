# Project Architecture Rules (Non-Obvious Only)

- This is a multi-member monorepo: backend lives in `apps/api/` (NestJS, TypeScript). Other members are scaffolding VSCode extension and AI features in separate branches — there is no shared workspace config yet.
- `moduleResolution: nodenext` with `isolatedModules: true` is enforced — new packages added to the monorepo must be ESM-compatible and export `package.json` `exports` maps.
- `emitDecoratorMetadata: true` is required for NestJS dependency injection — cannot be removed without breaking the DI container.
- E2e tests use a separate `test/jest-e2e.json` config (no coverage, different test regex) — do not fold e2e specs into the main jest config.
- `apps/api/dist/` is deleted on every build (`deleteOutDir: true` in nest-cli.json) — do not place any hand-written files there.
