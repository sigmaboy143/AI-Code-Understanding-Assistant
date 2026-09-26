import {
  ExplanationResponse,
  WhyResponse,
  RelationsResponse,
  DataFlowResponse,
  HistoryResponse,
  ImpactResponse,
  TestsResponse,
  DebugResponse,
  ArchitectureResponse,
  ExplanationMode,
  CodeContext,
} from "../types";

// Simulated network delay for realistic feel
const delay = (ms = 800) => new Promise((r) => setTimeout(r, ms));

export async function mockExplain(
  ctx: CodeContext,
  mode: ExplanationMode
): Promise<ExplanationResponse> {
  await delay();
  const modeDescriptions: Record<ExplanationMode, string> = {
    beginner:
      "This code finds a user in the database by their ID. Think of it like looking up someone's record in a filing cabinet using their unique number.",
    intermediate:
      "This performs an asynchronous database query using the ORM's `findById` method. It awaits the promise, returning `null` if no matching record exists.",
    advanced:
      "Calls the ORM's `findById` which constructs a `SELECT * FROM users WHERE id = $1` parameterized query. The async/await pattern suspends execution on the microtask queue until the connection pool resolves the query. Returns `null` if no row matches — callers should guard against null before dereferencing.",
  };
  return {
    what: "Retrieves a user record from the database using a unique identifier.",
    how: modeDescriptions[mode],
    why: "Needed to load user data before performing authorization checks or displaying profile information.",
    where: `${ctx.file ?? "src/auth/service.ts"} — used in validateUser(), getUserProfile(), and updateUser() functions.`,
    related: ["src/users/user.model.ts", "src/auth/auth.guard.ts", "src/users/users.service.ts"],
    tests: ["src/auth/auth.service.spec.ts", "src/users/users.service.spec.ts"],
    history: "Introduced in commit abc123 (PR #51) as part of the authentication refactor.",
    impact: "Changes here affect all endpoints that require user authentication.",
    confidence: "confirmed",
    evidence: [
      {
        file: ctx.file ?? "src/auth/service.ts",
        lines: [ctx.startLine ?? 40, ctx.endLine ?? 43],
        commit: "abc123",
        pr: "#51",
        description: "Original implementation",
      },
    ],
    mode,
  };
}

export async function mockWhy(ctx: CodeContext): Promise<WhyResponse> {
  await delay();
  return {
    reason: "This code exists to support user authentication and session management.",
    context:
      "Before this was introduced, the application had no centralized user lookup — each route was querying the database independently, causing inconsistency.",
    commits: [
      {
        hash: "abc123",
        message: "feat: add centralized user lookup service",
        author: "Jane Dev",
        date: "2024-03-15",
      },
      {
        hash: "def456",
        message: "refactor: extract user service to shared module",
        author: "Bob Engineer",
        date: "2024-04-02",
      },
    ],
    prs: [{ number: 51, title: "Authentication refactor", description: "Centralized user lookup" }],
    issues: ["Issue #23 — inconsistent user loading", "Issue #31 — duplicate DB calls"],
    confidence: "confirmed",
    evidence: [
      { file: ctx.file ?? "src/auth/service.ts", commit: "abc123", pr: "#51" },
    ],
  };
}

export async function mockRelations(ctx: CodeContext): Promise<RelationsResponse> {
  await delay();
  return {
    nodes: [
      { id: "n1", label: ctx.file ?? "auth/service.ts", type: "file" },
      { id: "n2", label: "users/user.model.ts", type: "file" },
      { id: "n3", label: "auth/auth.guard.ts", type: "file" },
      { id: "n4", label: "validateUser()", type: "function" },
      { id: "n5", label: "User DB Table", type: "database" },
      { id: "n6", label: "POST /auth/login", type: "api" },
    ],
    edges: [
      { from: "n6", to: "n4", label: "calls" },
      { from: "n4", to: "n1", label: "defined in" },
      { from: "n1", to: "n2", label: "imports" },
      { from: "n1", to: "n3", label: "used by" },
      { from: "n4", to: "n5", label: "queries" },
    ],
    confidence: "confirmed",
    evidence: [{ file: ctx.file ?? "src/auth/service.ts" }],
  };
}

export async function mockDataFlow(ctx: CodeContext): Promise<DataFlowResponse> {
  await delay();
  return {
    steps: [
      { id: "s1", label: "HTTP Request", type: "input", description: "POST /auth/login body: { email, password }" },
      { id: "s2", label: "AuthController", type: "function", file: "src/auth/auth.controller.ts", line: 12 },
      { id: "s3", label: "AuthService.login()", type: "service", file: "src/auth/auth.service.ts", line: 28 },
      { id: "s4", label: "User.findById()", type: "function", file: ctx.file ?? "src/auth/service.ts", line: ctx.startLine ?? 40 },
      { id: "s5", label: "PostgreSQL", type: "database", description: "SELECT * FROM users WHERE id = $1" },
      { id: "s6", label: "JWT Token", type: "output", description: "Signed token returned to client" },
    ],
    confidence: "inferred",
    evidence: [{ file: ctx.file ?? "src/auth/service.ts" }],
  };
}

export async function mockHistory(ctx: CodeContext): Promise<HistoryResponse> {
  await delay();
  return {
    summary: "This code has been stable for 3 months with 4 meaningful changes since its introduction.",
    commits: [
      { hash: "abc123", message: "feat: initial user lookup service", author: "Jane Dev", date: "2024-01-10" },
      { hash: "def456", message: "fix: handle null user gracefully", author: "Bob Engineer", date: "2024-02-03" },
      { hash: "ghi789", message: "perf: add index on user id column", author: "Alice Coder", date: "2024-03-20" },
      { hash: "jkl012", message: "refactor: move to async/await pattern", author: "Jane Dev", date: "2024-04-15" },
    ],
    confidence: "confirmed",
    evidence: [{ file: ctx.file ?? "src/auth/service.ts", commit: "abc123" }],
  };
}

export async function mockImpact(ctx: CodeContext): Promise<ImpactResponse> {
  await delay();
  return {
    root: ctx.selectedText?.trim().split("\n")[0] ?? "validateUser()",
    nodes: [
      { id: "i1", label: "AuthController.login()", type: "direct", file: "src/auth/auth.controller.ts" },
      { id: "i2", label: "AuthGuard", type: "direct", file: "src/auth/auth.guard.ts" },
      { id: "i3", label: "ProfileController", type: "indirect", file: "src/users/profile.controller.ts" },
      { id: "i4", label: "auth.service.spec.ts", type: "test", file: "src/auth/auth.service.spec.ts" },
      { id: "i5", label: "POST /auth/login", type: "api" },
      { id: "i6", label: "GET /profile", type: "api" },
    ],
    summary:
      "Changing this function directly affects 2 controllers and 1 guard. Indirectly, 3 API endpoints and 2 test suites would need validation.",
    confidence: "inferred",
    evidence: [{ file: ctx.file ?? "src/auth/service.ts" }],
  };
}

export async function mockTests(ctx: CodeContext): Promise<TestsResponse> {
  await delay();
  return {
    tests: [
      {
        file: "src/auth/auth.service.spec.ts",
        name: "should return user when valid id provided",
        description: "Verifies happy-path user lookup returns correct user object.",
        lines: [18, 30],
        coverage: 94,
      },
      {
        file: "src/auth/auth.service.spec.ts",
        name: "should return null when user not found",
        description: "Ensures null is returned gracefully when no user matches.",
        lines: [32, 44],
        coverage: 94,
      },
      {
        file: "src/users/users.service.spec.ts",
        name: "getUserById integration test",
        description: "Integration test against a real test database.",
        lines: [55, 70],
        coverage: 87,
      },
    ],
    summary: "3 tests found covering this code path. Overall coverage: ~91%.",
    confidence: "confirmed",
    evidence: [{ file: "src/auth/auth.service.spec.ts" }],
  };
}

export async function mockDebug(ctx: CodeContext, error?: string): Promise<DebugResponse> {
  await delay();
  return {
    error: error ?? "TypeError: Cannot read properties of null (reading 'id')",
    rootCause:
      "User.findById() returned null because the provided ID does not exist in the database, but the caller did not guard against null before accessing .id.",
    callChain: ["POST /auth/login", "AuthController.login()", "AuthService.login()", "User.findById(id)", "→ null.id ❌"],
    relatedCode: ["src/auth/auth.service.ts:42", "src/auth/auth.controller.ts:18"],
    recentChanges: [
      {
        hash: "jkl012",
        message: "refactor: remove explicit null check (assumed handled upstream)",
        author: "Jane Dev",
        date: "2024-04-15",
      },
    ],
    possibleCauses: [
      { cause: "Caller removed null guard in recent refactor", confidence: "confirmed" },
      { cause: "ID passed from client is malformed (non-numeric string)", confidence: "inferred" },
      { cause: "Database row was deleted between request stages", confidence: "unknown" },
    ],
    confidence: "inferred",
    evidence: [{ file: ctx.file ?? "src/auth/service.ts", lines: [40, 43] }],
  };
}

export async function mockArchitecture(): Promise<ArchitectureResponse> {
  await delay(1200);
  return {
    layers: [
      { id: "l1", label: "Frontend / Client", components: ["React App", "VS Code Extension"], description: "User interfaces and developer tools" },
      { id: "l2", label: "API Layer", components: ["AuthController", "UsersController", "ProfileController"], description: "HTTP endpoints and routing" },
      { id: "l3", label: "Service Layer", components: ["AuthService", "UsersService", "EmailService"], description: "Business logic and orchestration" },
      { id: "l4", label: "Data Layer", components: ["UserModel", "SessionModel", "PostgreSQL", "Redis Cache"], description: "Data persistence and caching" },
    ],
    description:
      "This is a standard layered NestJS application with a clear separation between API controllers, services, and data access.",
    confidence: "inferred",
  };
}
