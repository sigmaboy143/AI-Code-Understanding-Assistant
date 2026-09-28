import { jest } from '@jest/globals';

import {
  BadGatewayException,
  BadRequestException,
  GatewayTimeoutException,
  InternalServerErrorException,
  ServiceUnavailableException,
} from '@nestjs/common';
import { AiEngineAdapterProvider } from './ai-engine.adapter.js';
import {
  AiEngineClient,
  AiEngineClientError,
  type AiEngineClientErrorCode,
} from './ai-engine.client.js';
import type { AnalysisRequest } from '../interfaces/analysis-provider.interface.js';
import type { AiEngineAnalysisType } from '../contracts/ai-engine-request.contract.js';
import type {
  AiEngineConfidenceLevel,
  AiEngineEvidenceItem,
  AiEngineEvidenceSourceType,
  AiEngineResponseContract,
} from '../contracts/ai-engine-response.contract.js';

// ---------------------------------------------------------------------------
// Helpers

function makeAdapter(
  clientPost: jest.Mock = jest.fn(),
): AiEngineAdapterProvider {
  const client = { post: clientPost } as unknown as AiEngineClient;
  return new AiEngineAdapterProvider(client);
}

const BASE_REQUEST: AnalysisRequest = {
  requestId: 'req-001',
  language: 'typescript',
  code: 'const x = 1;',
  filePath: 'src/index.ts',
  context: 'some context',
};

const BASE_RESPONSE: AiEngineResponseContract = {
  summary: 'Assigns a constant.',
  metadata: { language: 'typescript', file_path: 'src/index.ts', analyses: [] },
  confidence: {
    level: 'CONFIRMED',
    evidence: [
      {
        source_type: 'source_code',
        file_path: 'src/index.ts',
        line_start: 1,
        line_end: 1,
        chunk_id: 'chunk-42',
        description: 'Variable declaration found.',
      },
    ],
    notes: 'Directly supported by the submitted source code.',
  },
  explanation: null,
  structure: null,
  dependencies: null,
  improvements: null,
};

// ---------------------------------------------------------------------------

/** BASE_RESPONSE with its single evidence item overridden. */
function withEvidence(
  patch: Partial<AiEngineEvidenceItem>,
): AiEngineResponseContract {
  return {
    ...BASE_RESPONSE,
    confidence: {
      ...BASE_RESPONSE.confidence,
      evidence: [
        { ...BASE_RESPONSE.confidence.evidence[0]!, ...patch },
      ],
    },
  };
}

describe('AiEngineAdapterProvider', () => {
  // ── Request mapping ──────────────────────────────────────────────────────

  it('maps code to source_code', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(post).toHaveBeenCalledWith(
      expect.objectContaining({ source_code: BASE_REQUEST.code }),
    );
  });

  it('maps filePath to file_path', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(post).toHaveBeenCalledWith(
      expect.objectContaining({ file_path: BASE_REQUEST.filePath }),
    );
  });

  it('maps undefined filePath to file_path: null', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    const req = { ...BASE_REQUEST, filePath: undefined };
    await makeAdapter(post).analyzeCode(req);
    expect(post).toHaveBeenCalledWith(
      expect.objectContaining({ file_path: null }),
    );
  });

  it('maps context when defined', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(post).toHaveBeenCalledWith(
      expect.objectContaining({ context: BASE_REQUEST.context }),
    );
  });

  it('maps undefined context to context: null', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    const req = { ...BASE_REQUEST, context: undefined };
    await makeAdapter(post).analyzeCode(req);
    expect(post).toHaveBeenCalledWith(
      expect.objectContaining({ context: null }),
    );
  });

  it('always sends question: null', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(post).toHaveBeenCalledWith(
      expect.objectContaining({ question: null }),
    );
  });

  // ── analyses ──────────────────────────────────────────────────────────────
  //
  // CodeUnderstandingRequest.analyses has min_length=1, so `[]` is rejected by
  // the AI Engine with 422. NestJS has no explicit analysis selection, so the
  // key must be absent and the AI Engine must apply its own default of all five
  // AnalysisType values.

  it('omits analyses entirely — no explicit selection exists in AnalysisRequest', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    await makeAdapter(post).analyzeCode(BASE_REQUEST);
    const sent = post.mock.calls[0]![0] as Record<string, unknown>;
    expect('analyses' in sent).toBe(false);
    expect(Object.keys(sent).sort()).toEqual([
      'context',
      'file_path',
      'language',
      'question',
      'source_code',
    ]);
  });

  it('never sends analyses: []', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    await makeAdapter(post).analyzeCode(BASE_REQUEST);
    const sent = post.mock.calls[0]![0] as Record<string, unknown>;
    expect(sent.analyses).not.toEqual([]);
  });

  it('omits analyses for every AnalysisRequest shape', async () => {
    const requests: AnalysisRequest[] = [
      BASE_REQUEST,
      { ...BASE_REQUEST, filePath: undefined, context: undefined },
      { requestId: 'r', language: 'python', code: 'x = 1' },
    ];
    for (const request of requests) {
      const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
      await makeAdapter(post).analyzeCode(request);
      const sent = post.mock.calls[0]![0] as Record<string, unknown>;
      expect('analyses' in sent).toBe(false);
    }
  });

  it('the five AnalysisType values remain the valid contract set', () => {
    // Compile-time and runtime assertion that the contract union is exactly the
    // AI Engine's AnalysisType enum. An invalid value is a type error.
    const all: AiEngineAnalysisType[] = [
      'explanation',
      'error_explanation',
      'structure',
      'dependencies',
      'improvements',
    ];
    expect(all).toHaveLength(5);
    expect([...all].sort()).toEqual([
      'dependencies',
      'error_explanation',
      'explanation',
      'improvements',
      'structure',
    ]);
  });

  // ── Response mapping ─────────────────────────────────────────────────────

  it('uses requestId from the original request', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.requestId).toBe(BASE_REQUEST.requestId);
  });

  it('uses language from response metadata', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.language).toBe(BASE_RESPONSE.metadata.language);
  });

  it('falls back to request language when metadata.language is empty', async () => {
    const response = {
      ...BASE_RESPONSE,
      metadata: { ...BASE_RESPONSE.metadata, language: '' },
    };
    const post = jest.fn().mockResolvedValue(response);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.language).toBe(BASE_REQUEST.language);
  });

  it('maps summary from AI Engine response', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.summary).toBe(BASE_RESPONSE.summary);
  });

  it('symbols is always []', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.symbols).toEqual([]);
  });

  it('relationships is always []', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.relationships).toEqual([]);
  });

  // ── Confidence mapping ────────────────────────────────────────────────────
  //
  // The AI Engine's ConfidenceLevel enum is CONFIRMED | INFERRED | UNKNOWN.
  // Each is preserved as a distinct level; none is collapsed into high/medium.

  it.each([
    ['CONFIRMED', 'confirmed'],
    ['INFERRED', 'inferred'],
    ['UNKNOWN', 'unknown'],
  ] as const)(
    'preserves AI Engine confidence level %s → %s',
    async (raw, expected) => {
      const response = {
        ...BASE_RESPONSE,
        confidence: { ...BASE_RESPONSE.confidence, level: raw },
      };
      const post = jest.fn().mockResolvedValue(response);
      const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
      expect(result.confidence.level).toBe(expected);
    },
  );

  it('does not collapse CONFIRMED into high', async () => {
    const response = {
      ...BASE_RESPONSE,
      confidence: { ...BASE_RESPONSE.confidence, level: 'CONFIRMED' },
    };
    const post = jest.fn().mockResolvedValue(response);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.confidence.level).not.toBe('high');
    expect(result.confidence.level).toBe('confirmed');
  });

  it('does not collapse INFERRED into medium', async () => {
    const response = {
      ...BASE_RESPONSE,
      confidence: { ...BASE_RESPONSE.confidence, level: 'INFERRED' },
    };
    const post = jest.fn().mockResolvedValue(response);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.confidence.level).not.toBe('medium');
    expect(result.confidence.level).toBe('inferred');
  });

  it.each([
    ['HIGH', 'high'],
    ['MEDIUM', 'medium'],
    ['LOW', 'low'],
    ['SOMETHING_ELSE', 'unknown'],
  ] as const)(
    'retains pre-existing mapping %s → %s',
    async (raw, expected) => {
      // 'HIGH' | 'MEDIUM' | 'LOW' | 'SOMETHING_ELSE' are NOT part of the AI
      // Engine's current ConfidenceLevel enum. They are cast in deliberately to
      // prove the legacy mapping is retained for providers that predate the
      // three-state contract, and that unrecognised input stays 'unknown'.
      const response = {
        ...BASE_RESPONSE,
        confidence: {
          ...BASE_RESPONSE.confidence,
          level: raw as AiEngineConfidenceLevel,
        },
      };
      const post = jest.fn().mockResolvedValue(response);
      const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
      expect(result.confidence.level).toBe(expected);
    },
  );

  it('accepts lowercase confidence levels from the wire', async () => {
    const response = {
      ...BASE_RESPONSE,
      confidence: {
        ...BASE_RESPONSE.confidence,
        level: 'inferred' as AiEngineConfidenceLevel,
      },
    };
    const post = jest.fn().mockResolvedValue(response);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.confidence.level).toBe('inferred');
  });

  it('score is always undefined — AI Engine provides no numeric score', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.confidence.score).toBeUndefined();
  });

  it('UNKNOWN level produces score: undefined — not zero', async () => {
    const response = {
      ...BASE_RESPONSE,
      confidence: { ...BASE_RESPONSE.confidence, level: 'UNKNOWN' },
    };
    const post = jest.fn().mockResolvedValue(response);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.confidence.score).toBeUndefined();
    expect(result.confidence.level).toBe('unknown');
  });

  it('model is always undefined', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.confidence.model).toBeUndefined();
  });

  it('maps confidence.notes to reasoning', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.confidence.reasoning).toBe(BASE_RESPONSE.confidence.notes);
  });

  it('sets reasoning to undefined when notes is empty string', async () => {
    const response = {
      ...BASE_RESPONSE,
      confidence: { ...BASE_RESPONSE.confidence, notes: '' },
    };
    const post = jest.fn().mockResolvedValue(response);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.confidence.reasoning).toBeUndefined();
  });

  // ── Evidence mapping ──────────────────────────────────────────────────────

  it('produces one Evidence item per AI Engine evidence entry', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.evidence).toHaveLength(1);
  });

  it('empty evidence array produces evidence: []', async () => {
    const response = {
      ...BASE_RESPONSE,
      confidence: { ...BASE_RESPONSE.confidence, evidence: [] },
    };
    const post = jest.fn().mockResolvedValue(response);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.evidence).toEqual([]);
  });

  it('preserves source_type in structured field', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.evidence[0]?.sourceType).toBe('source_code');
  });

  it('preserves file_path in structured field', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.evidence[0]?.filePath).toBe('src/index.ts');
  });

  it('maps null file_path to undefined in structured field', async () => {
    const response = {
      ...BASE_RESPONSE,
      confidence: {
        ...BASE_RESPONSE.confidence,
        evidence: [
          { ...BASE_RESPONSE.confidence.evidence[0]!, file_path: null },
        ],
      },
    };
    const post = jest.fn().mockResolvedValue(response);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.evidence[0]?.filePath).toBeUndefined();
  });

  it('preserves line_start and line_end in structured fields', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.evidence[0]?.lineStart).toBe(1);
    expect(result.evidence[0]?.lineEnd).toBe(1);
  });

  it('preserves chunk_id in structured field', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.evidence[0]?.chunkId).toBe('chunk-42');
  });

  it('includes description in detail', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.evidence[0]?.detail).toContain('Variable declaration found.');
  });

  it('appends file and line info to detail when present', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.evidence[0]?.detail).toContain('file:src/index.ts');
    expect(result.evidence[0]?.detail).toContain('lines:1-1');
  });

  it('maps source_type to kind by identity — never inventing a bucket', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE); // source_type: 'source_code'
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.evidence[0]?.kind).toBe('source_code');
  });

  it('does not classify source_code as syntax', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.evidence[0]?.kind).not.toBe('syntax');
  });

  it('does not classify documentation as semantic', async () => {
    const response = withEvidence({ source_type: 'documentation' });
    const post = jest.fn().mockResolvedValue(response);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.evidence[0]?.kind).toBe('documentation');
    expect(result.evidence[0]?.kind).not.toBe('semantic');
  });

  it.each([
    'source_code',
    'retrieved_chunk',
    'file',
    'documentation',
    'test',
    'git_commit',
  ] as const)('preserves AI Engine source type %s verbatim', async (sourceType) => {
    const post = jest.fn().mockResolvedValue(withEvidence({ source_type: sourceType }));
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.evidence[0]?.sourceType).toBe(sourceType);
    expect(result.evidence[0]?.kind).toBe(sourceType);
  });

  it('no AI Engine source type is classified as ai', async () => {
    const all: AiEngineEvidenceSourceType[] = [
      'source_code',
      'retrieved_chunk',
      'file',
      'documentation',
      'test',
      'git_commit',
    ];
    for (const sourceType of all) {
      const post = jest
        .fn()
        .mockResolvedValue(withEvidence({ source_type: sourceType }));
      const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
      expect(result.evidence[0]?.kind).not.toBe('ai');
    }
  });

  it('does not fabricate evidence — only the AI Engine evidence is emitted', async () => {
    const response = withEvidence({ source_type: 'source_code' });
    const post = jest.fn().mockResolvedValue(response);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.evidence).toHaveLength(1);
    expect(
      result.evidence.filter(
        (e) => e.sourceType === 'test' || e.sourceType === 'git_commit',
      ),
    ).toEqual([]);
  });

  it('never invents test or git_commit evidence when none was supplied', async () => {
    const response = withEvidence({ source_type: 'source_code' });
    const post = jest.fn().mockResolvedValue(response);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.evidence.map((e) => e.sourceType)).toEqual(['source_code']);
  });

  it('handles a null description without stringifying null', async () => {
    const response = withEvidence({
      source_type: 'source_code',
      description: null,
    });
    const post = jest.fn().mockResolvedValue(response);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.evidence[0]?.detail).not.toContain('null');
    expect(result.evidence[0]?.detail).toContain('file:src/index.ts');
  });

  // ── Nullable AI fields ────────────────────────────────────────────────────

  it('explanation: null does not produce symbols', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE); // explanation is null
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.symbols).toEqual([]);
  });

  it('structure: null does not produce symbols', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE); // structure is null
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.symbols).toEqual([]);
  });

  it('dependencies: null does not produce relationships', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE); // dependencies is null
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.relationships).toEqual([]);
  });

  it('improvements: null is ignored', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE); // improvements is null
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result).toBeDefined();
  });

  // ── Error mapping ─────────────────────────────────────────────────────────

  it.each([
    ['validation_error', BadRequestException],
    ['provider_unavailable', ServiceUnavailableException],
    ['provider_timeout', GatewayTimeoutException],
    ['provider_error', BadGatewayException],
    ['internal_error', InternalServerErrorException],
    ['network_error', ServiceUnavailableException],
    ['timeout', GatewayTimeoutException],
  ] as [AiEngineClientErrorCode, new (...args: unknown[]) => Error][])(
    'maps AiEngineClientError(%s) to correct NestJS exception',
    async (code, ExceptionClass) => {
      const post = jest.fn().mockRejectedValue(new AiEngineClientError(code));
      await expect(makeAdapter(post).analyzeCode(BASE_REQUEST)).rejects.toBeInstanceOf(
        ExceptionClass,
      );
    },
  );

  it('thrown NestJS exception message does not contain upstream AI Engine message', async () => {
    const post = jest
      .fn()
      .mockRejectedValue(
        new AiEngineClientError('validation_error', 'internal FastAPI detail'),
      );

    let caughtError: unknown;

    try {
      await makeAdapter(post).analyzeCode(BASE_REQUEST);
      throw new Error('Expected analyzeCode() to reject');
    } catch (error) {
      caughtError = error;
    }

    expect(caughtError).toHaveProperty('status', 400);

    const message =
      typeof caughtError === 'object' &&
      caughtError !== null &&
      'message' in caughtError
        ? (caughtError as { message?: unknown }).message
        : undefined;

    expect(message).not.toContain('internal FastAPI detail');
  });
});
