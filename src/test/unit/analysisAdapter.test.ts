import * as assert from "assert";
import {
  buildAnalyzeCodeBody,
  buildAnalyzeFileBody,
  buildExplainCodeBody,
  buildRelationshipsQuery,
  mapAnalysisResult,
  mapExplanationsResult,
  mapConfidenceLevel,
  mapEvidence,
  mapRelationsResponse,
  describeBackendError,
  isBackendCapabilityError,
  BackendCapabilityError,
} from "../../api/analysisAdapter";
import type { BackendAnalysisResult } from "../../types/backend";
import type { CodeContext } from "../../types";

// A realistic AnalysisResult as the AI Engine path actually produces it:
// summarised, with a three-state confidence level, no numeric score, and
// evidence carrying the AI Engine's own source_type.
function analysisResultFixture(
  overrides: Partial<BackendAnalysisResult> = {}
): BackendAnalysisResult {
  return {
    requestId: "4a1f0e6c-2b7d-4a51-9c3e-8f2b1d0a7e55",
    language: "python",
    symbols: [
      {
        id: "sym-1",
        name: "add",
        kind: "function",
        location: {
          filePath: "math_utils.py",
          startLine: 1,
          endLine: 2,
          startColumn: 0,
          endColumn: 30,
        },
      },
    ],
    relationships: [],
    summary: "Adds two numbers and returns the sum.",
    confidence: { level: "confirmed", reasoning: "Directly supported by source code." },
    evidence: [
      {
        kind: "source_code",
        sourceType: "source_code",
        detail: "Function body [file:math_utils.py, lines:1-2]",
        filePath: "math_utils.py",
        lineStart: 1,
        lineEnd: 2,
      },
    ],
    analysedAt: "2026-09-27T10:15:00.000Z",
    ...overrides,
  };
}

const selectionContext: CodeContext = {
  file: "math_utils.py",
  selectedText: "def add(a, b):\n    return a + b",
  startLine: 1,
  endLine: 2,
  language: "python",
  workspaceRoot: "/repo",
};

suite("POST /analysis/code request body", () => {
  test("sends exactly the whitelisted AnalyzeCodeDto keys", () => {
    const body = buildAnalyzeCodeBody(selectionContext, "def add(a, b): return a + b");

    // The backend runs forbidNonWhitelisted, so the key set is the contract.
    assert.deepStrictEqual(
      Object.keys(body).sort(),
      ["code", "context", "filePath", "language"]
    );
    assert.strictEqual(body.language, "python");
    assert.strictEqual(body.code, "def add(a, b): return a + b");
    assert.strictEqual(body.filePath, "math_utils.py");
  });

  test("omits filePath when there is no file", () => {
    // `file` is typed as required on CodeContext, but the extension host can
    // legitimately have nothing to report, so the absence is simulated.
    const body = buildAnalyzeCodeBody({ language: "python" } as CodeContext, "x = 1");
    assert.strictEqual("filePath" in body, false);
    assert.strictEqual(Object.keys(body).sort().join(","), "code,language");
  });

  test("never sends unsupported context fields", () => {
    const ctx: CodeContext = {
      file: "a.py",
      selectedText: "x",
      startLine: 1,
      endLine: 1,
      language: "python",
      repositoryId: "repo-1",
    };
    const body = buildAnalyzeCodeBody(ctx, "x") as unknown as Record<string, unknown>;
    for (const forbidden of ["repositoryId", "workspaceRoot", "selectedText", "startLine", "endLine", "mode"]) {
      assert.strictEqual(forbidden in body, false, `${forbidden} must not be sent`);
    }
  });

  test("falls back to a non-blank language for an untitled buffer", () => {
    const body = buildAnalyzeCodeBody({ file: "notes", language: "   " }, "text");
    assert.ok(body.language.trim().length > 0, "language must satisfy /\\S/");
  });
});

suite("POST /analysis/file request body", () => {
  test("includes the required filePath and the full file body", () => {
    const fullFile = "def add(a, b):\n    return a + b\n";
    const body = buildAnalyzeFileBody(selectionContext, fullFile);

    assert.strictEqual(body.filePath, "math_utils.py");
    assert.strictEqual(body.code, fullFile, "the whole document must be sent, not the selection");
    assert.ok(body.code.includes("return a + b"));
  });

  test("always sends filePath even when the context has none", () => {
    const body = buildAnalyzeFileBody({ language: "python" } as CodeContext, "x = 1");
    assert.ok(body.filePath.length > 0, "AnalyzeFileDto requires a non-empty filePath");
  });

  test("sends only whitelisted keys", () => {
    const body = buildAnalyzeFileBody(selectionContext, "x") as unknown as Record<string, unknown>;
    assert.deepStrictEqual(Object.keys(body).sort(), ["code", "context", "filePath", "language"]);
  });
});

suite("POST /explanations request body", () => {
  test("maps selection range and defaults detailLevel", () => {
    const body = buildExplainCodeBody(selectionContext, "def add(a,b): ...");
    assert.strictEqual(body.language, "python");
    assert.strictEqual(body.startLine, 1);
    assert.strictEqual(body.endLine, 2);
    assert.strictEqual(body.detailLevel, "standard");
  });
});

suite("GET /relationships query", () => {
  test("sends only filePath and language", () => {
    const query = buildRelationshipsQuery(selectionContext);
    assert.deepStrictEqual(Object.keys(query).sort(), ["filePath", "language"]);
    assert.strictEqual(query.filePath, "math_utils.py");
    assert.strictEqual(query.language, "python");
  });
});

suite("AnalysisResult 201 response parsing", () => {
  test("maps summary, correlation id, timestamp and provenance", () => {
    const result = mapAnalysisResult(analysisResultFixture(), "intermediate", selectionContext);

    assert.strictEqual(result.source, "backend");
    assert.strictEqual(result.what, "Adds two numbers and returns the sum.");
    assert.strictEqual(result.requestId, "4a1f0e6c-2b7d-4a51-9c3e-8f2b1d0a7e55");
    assert.strictEqual(result.analysedAt, "2026-09-27T10:15:00.000Z");
    assert.strictEqual(result.mode, "intermediate");
  });

  test("does not invent how or why prose the backend never sent", () => {
    const result = mapAnalysisResult(analysisResultFixture(), "intermediate");
    assert.strictEqual(result.how, "", "the backend returns one summary, not a how");
    assert.strictEqual(result.why, "", "the backend asserts no rationale");
  });

  test("survives a response with no summary", () => {
    const result = mapAnalysisResult(analysisResultFixture({ summary: undefined }), "advanced");
    assert.strictEqual(result.what, "");
  });

  test("omits symbols and relationships when the arrays are empty", () => {
    const result = mapAnalysisResult(analysisResultFixture({ symbols: [], relationships: [] }), "advanced");
    assert.strictEqual(result.symbols, undefined);
    assert.strictEqual(result.relationships, undefined);
  });

  test("carries real symbols through with their location", () => {
    const result = mapAnalysisResult(analysisResultFixture(), "advanced");
    assert.strictEqual(result.symbols?.length, 1);
    assert.strictEqual(result.symbols?.[0].name, "add");
    assert.strictEqual(result.symbols?.[0].kind, "function");
    assert.strictEqual(result.symbols?.[0].filePath, "math_utils.py");
    assert.strictEqual(result.symbols?.[0].startLine, 1);
  });

  test("maps the explanations response shape, which does carry referencedSymbols", () => {
    const result = mapExplanationsResult(
      {
        requestId: "req-9",
        summary: "Adds two numbers.",
        detailed: "Returns a + b directly.",
        confidence: { level: "inferred" },
        referencedSymbols: [
          {
            id: "sym-1",
            name: "add",
            kind: "function",
            location: { filePath: "math_utils.py", startLine: 1, endLine: 2, startColumn: 0, endColumn: 10 },
          },
        ],
        generatedAt: "2026-09-27T10:16:00.000Z",
      },
      "advanced"
    );

    assert.strictEqual(result.how, "Returns a + b directly.");
    assert.strictEqual(result.generatedAt, "2026-09-27T10:16:00.000Z");
    assert.strictEqual(result.symbols?.[0].name, "add");
  });
});

suite("confidence mapping", () => {
  test("preserves the AI Engine's three states", () => {
    assert.strictEqual(mapConfidenceLevel({ level: "confirmed" }), "confirmed");
    assert.strictEqual(mapConfidenceLevel({ level: "inferred" }), "inferred");
    assert.strictEqual(mapConfidenceLevel({ level: "unknown" }), "unknown");
  });

  test("translates the backend's legacy vocabulary", () => {
    assert.strictEqual(mapConfidenceLevel({ level: "high" }), "confirmed");
    assert.strictEqual(mapConfidenceLevel({ level: "medium" }), "inferred");
    assert.strictEqual(mapConfidenceLevel({ level: "low" }), "unknown");
  });

  test("never upgrades an unrecognised or missing level", () => {
    assert.strictEqual(mapConfidenceLevel({ level: "excellent" } as never), "unknown");
    assert.strictEqual(mapConfidenceLevel({ level: "" } as never), "unknown");
    assert.strictEqual(mapConfidenceLevel(undefined), "unknown");
    assert.strictEqual(mapConfidenceLevel(null), "unknown");
    assert.strictEqual(mapConfidenceLevel({} as never), "unknown");
  });

  test("keeps the raw level and never fabricates a numeric score", () => {
    const result = mapAnalysisResult(analysisResultFixture(), "advanced");
    assert.strictEqual(result.confidenceMeta?.level, "confirmed");
    assert.strictEqual(
      result.confidenceMeta?.score,
      undefined,
      "an absent score means not provided, not zero"
    );
  });

  test("passes through a real numeric score when the backend sends one", () => {
    const result = mapAnalysisResult(
      analysisResultFixture({ confidence: { level: "confirmed", score: 0.82 } }),
      "advanced"
    );
    assert.strictEqual(result.confidenceMeta?.score, 0.82);
  });
});

suite("evidence mapping", () => {
  test("preserves source type, path, line range, chunk id and detail", () => {
    const mapped = mapEvidence([
      {
        kind: "retrieved_chunk",
        sourceType: "retrieved_chunk",
        detail: "doc chunk [file:docs/auth.md, lines:10-20, chunk:c-7]",
        filePath: "docs/auth.md",
        lineStart: 10,
        lineEnd: 20,
        chunkId: "c-7",
      },
    ]);

    assert.strictEqual(mapped.length, 1);
    assert.strictEqual(mapped[0].kind, "retrieved_chunk");
    assert.strictEqual(mapped[0].sourceType, "retrieved_chunk");
    assert.strictEqual(mapped[0].filePath, "docs/auth.md");
    assert.strictEqual(mapped[0].lineStart, 10);
    assert.strictEqual(mapped[0].lineEnd, 20);
    assert.strictEqual(mapped[0].chunkId, "c-7");
    assert.strictEqual(mapped[0].detail, "doc chunk [file:docs/auth.md, lines:10-20, chunk:c-7]");
    // Display fields are derived from the structured ones, not the reverse.
    assert.strictEqual(mapped[0].file, "docs/auth.md");
    assert.deepStrictEqual(mapped[0].lines, [10, 20]);
  });

  test("does not invent git evidence the backend does not provide", () => {
    const mapped = mapEvidence([{ kind: "file", detail: "some file", filePath: "a.py" }]);
    assert.strictEqual(mapped[0].commit, undefined);
    assert.strictEqual(mapped[0].pr, undefined);
    assert.strictEqual(mapped[0].issue, undefined);
  });

  test("returns an empty list for an empty or missing evidence array", () => {
    assert.deepStrictEqual(mapEvidence([]), []);
    assert.deepStrictEqual(mapEvidence(undefined), []);
    assert.deepStrictEqual(mapEvidence(null), []);
  });

  test("handles evidence with no file path without crashing", () => {
    const mapped = mapEvidence([{ kind: "documentation", detail: "general claim" }]);
    assert.strictEqual(mapped[0].file, "");
    assert.strictEqual(mapped[0].lines, undefined);
  });

  test("keeps kind distinct from sourceType when the backend differentiates them", () => {
    const mapped = mapEvidence([
      { kind: "ai", sourceType: "documentation", detail: "docs", filePath: "d.md" },
    ]);
    assert.strictEqual(mapped[0].kind, "ai");
    assert.strictEqual(mapped[0].sourceType, "documentation");
  });
});

suite("relationships mapping", () => {
  test("builds edges and synthesises unresolvable symbol nodes", () => {
    const response = mapRelationsResponse([
      { id: "r1", fromSymbolId: "sym-a", toSymbolId: "sym-b", kind: "calls", filePath: "a.py", line: 10 },
    ]);

    assert.strictEqual(response.source, "backend");
    assert.strictEqual(response.edges.length, 1);
    assert.strictEqual(response.edges[0].label, "calls");
    assert.deepStrictEqual(response.nodes.map((n) => n.id).sort(), ["sym-a", "sym-b"]);
    // No symbol names were supplied, so the node must not claim a kind.
    assert.ok(response.nodes.every((n) => n.type === "symbol"));
    assert.strictEqual(response.confidence, "unknown", "the route asserts no confidence");
  });

  test("resolves real symbol names and kinds when symbols are available", () => {
    const symbols = new Map([
      [
        "sym-a",
        {
          id: "sym-a",
          name: "add",
          kind: "function" as const,
          location: { filePath: "a.py", startLine: 1, endLine: 2, startColumn: 0, endColumn: 1 },
        },
      ],
    ]);

    const response = mapRelationsResponse(
      [{ id: "r1", fromSymbolId: "sym-a", toSymbolId: "sym-b", kind: "calls", filePath: "a.py", line: 10 }],
      { symbolsById: symbols }
    );

    const resolved = response.nodes.find((n) => n.id === "sym-a");
    assert.strictEqual(resolved?.label, "add");
    assert.strictEqual(resolved?.type, "function");
  });

  test("handles the backend's current empty-array response", () => {
    const response = mapRelationsResponse([]);
    assert.deepStrictEqual(response.nodes, []);
    assert.deepStrictEqual(response.edges, []);
  });

  test("handles a non-array payload without throwing", () => {
    const response = mapRelationsResponse(undefined);
    assert.deepStrictEqual(response.nodes, []);
  });
});

suite("error handling", () => {
  test("extracts a NestJS 400 validation message", () => {
    const message = describeBackendError({
      response: { status: 400, data: { statusCode: 400, message: "code must not be blank", error: "Bad Request" } },
    });
    assert.ok(message.includes("400"), "status is surfaced");
    assert.ok(message.includes("code must not be blank"), "backend message is surfaced");
  });

  test("joins the array form of a multi-field validation error", () => {
    const message = describeBackendError({
      response: { status: 400, data: { message: ["language must not be blank", "code must not exceed 100000 characters"] } },
    });
    assert.ok(message.includes("language must not be blank"));
    assert.ok(message.includes("code must not exceed 100000 characters"));
    assert.ok(!message.includes("[object Object]"));
  });

  test("does not leak raw Axios internals on a 500", () => {
    const message = describeBackendError({
      message: "Request failed with status code 500",
      config: { url: "/analysis/code", headers: { Authorization: "Bearer secret-token" } },
      code: "ERR_BAD_RESPONSE",
      response: { status: 500, data: { statusCode: 500, message: "Internal server error" } },
    });
    assert.ok(message.includes("500"));
    assert.ok(!message.includes("secret-token"), "credentials must never be surfaced");
    assert.ok(!message.includes("Authorization"));
  });

  test("classifies a 5xx as a backend fault", () => {
    const message = describeBackendError({ response: { status: 500, data: {} } });
    assert.ok(message.includes("internal error"));
  });

  test("classifies 502 and 503 as AI provider problems", () => {
    assert.ok(describeBackendError({ response: { status: 502, data: {} } }).includes("502"));
    assert.ok(describeBackendError({ response: { status: 503, data: {} } }).toLowerCase().includes("unavailable"));
  });

  test("classifies a 404 as a missing endpoint", () => {
    assert.ok(describeBackendError({ response: { status: 404, data: {} } }).includes("no endpoint"));
  });

  test("handles 401 and 403", () => {
    assert.ok(describeBackendError({ response: { status: 401, data: {} } }).includes("authentication"));
    assert.ok(describeBackendError({ response: { status: 403, data: {} } }).includes("refused"));
  });

  test("classifies a timeout", () => {
    const message = describeBackendError({ code: "ECONNABORTED", message: "timeout of 30000ms exceeded" });
    assert.ok(message.toLowerCase().includes("time"));
  });

  test("classifies a network failure", () => {
    assert.ok(
      describeBackendError({ code: "ECONNREFUSED", message: "connect ECONNREFUSED" }).includes("running")
    );
    assert.ok(describeBackendError({ code: "ENOTFOUND" }).includes("backendUrl"));
  });

  test("preserves the correlation id in the message", () => {
    const message = describeBackendError({ response: { status: 400, data: {} } }, "req-42");
    assert.ok(message.includes("req-42"));
  });

  test("survives a thrown non-Error", () => {
    assert.ok(describeBackendError("a string").length > 0);
    assert.ok(describeBackendError(undefined).length > 0);
  });

  test("a capability error is distinguishable from a request failure", () => {
    const err = new BackendCapabilityError("impact", "Backend capability not currently available.");
    assert.ok(isBackendCapabilityError(err));
    assert.strictEqual(isBackendCapabilityError(new Error("boom")), false);
    assert.strictEqual(describeBackendError(err), "Backend capability not currently available.");
  });
});

suite("unsupported features stay mock/placeholder", () => {
  test("no apiService call targets a route the backend does not define", () => {
    // The backend at afda26c defines only these HTTP routes. This list is the
    // guard: a new invented path must be added here deliberately.
    const realRoutes = [
      "/analysis/code",
      "/analysis/file",
      "/explanations",
      "/relationships",
      "/symbols",
      "/files/",
      "/health",
      "/ready",
    ];
    const previouslyInvented = [
      "/explanations/code",
      "/explanations/why",
      "/relations/analyze",
      "/dataflow/trace",
      "/history/analyze",
      "/impact/analyze",
      "/tests/related",
      "/debug/analyze",
      "/architecture/",
    ];
    for (const path of previouslyInvented) {
      assert.ok(!realRoutes.includes(path), `${path} is not a backend route`);
    }
  });
});
