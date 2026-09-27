# Project Coding Rules (Non-Obvious Only)

- All commands must run from `apps/api/`, not the repo root — there is no root-level package.json.
- Invoke jest with `node --experimental-vm-modules ./node_modules/jest/bin/jest.js` — calling `jest` or `npx jest` directly will fail.
- To run a single test: append the file path after the jest invocation (no `--testPathPattern` needed).
- Float promises are an **error**: always `void expr` or `await expr` — bare async calls at statement level will fail linting.
- Use `.js` extensions in relative imports (e.g. `import { Foo } from './foo.js'`) because `moduleResolution: nodenext` enforces ESM-style resolution at compile time.
- `typescript/no-explicit-any` is disabled — using `any` is allowed by project policy.
- `strictPropertyInitialization` is off — constructor-injected NestJS providers don't need the `!` assertion suffix.
