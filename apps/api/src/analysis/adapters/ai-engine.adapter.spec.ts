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
import type { AiEngineResponseContract } from '../contracts/ai-engine-response.contract.js';

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
    level: 'HIGH',
    evidence: [
      {
        source_type: 'semantic_analysis',
        file_path: 'src/index.ts',
        line_start: 1,
        line_end: 1,
        chunk_id: 'chunk-42',
        description: 'Variable declaration found.',
      },
    ],
    notes: 'High confidence response.',
  },
  explanation: null,
  structure: null,
  dependencies: null,
  improvements: null,
};

// ---------------------------------------------------------------------------

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

  it('always sends analyses: []', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE);
    await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(post).toHaveBeenCalledWith(
      expect.objectContaining({ analyses: [] }),
    );
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

  it.each([
    ['HIGH', 'high'],
    ['MEDIUM', 'medium'],
    ['LOW', 'low'],
    ['UNKNOWN', 'unknown'],
    ['SOMETHING_ELSE', 'unknown'],
  ] as const)(
    'normalises confidence level %s → %s',
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
    expect(result.evidence[0]?.sourceType).toBe('semantic_analysis');
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

  it('maps semantic source_type to kind: semantic', async () => {
    const post = jest.fn().mockResolvedValue(BASE_RESPONSE); // source_type: 'semantic_analysis'
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.evidence[0]?.kind).toBe('semantic');
  });

  it('maps syntax source_type to kind: syntax', async () => {
    const response = {
      ...BASE_RESPONSE,
      confidence: {
        ...BASE_RESPONSE.confidence,
        evidence: [
          { ...BASE_RESPONSE.confidence.evidence[0]!, source_type: 'ast_parser' },
        ],
      },
    };
    const post = jest.fn().mockResolvedValue(response);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.evidence[0]?.kind).toBe('syntax');
  });

  it('maps unrecognised source_type to kind: ai', async () => {
    const response = {
      ...BASE_RESPONSE,
      confidence: {
        ...BASE_RESPONSE.confidence,
        evidence: [
          { ...BASE_RESPONSE.confidence.evidence[0]!, source_type: 'llm_reasoning' },
        ],
      },
    };
    const post = jest.fn().mockResolvedValue(response);
    const result = await makeAdapter(post).analyzeCode(BASE_REQUEST);
    expect(result.evidence[0]?.kind).toBe('ai');
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
