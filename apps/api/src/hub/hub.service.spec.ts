/**
 * Unit tests for HubService
 *
 * Proves:
 * - /ask returns a non-empty grounded answer with evidence.
 * - /debug returns a non-empty rootCause and fix when evidence supports it.
 * - enrichedSummary is populated when AI Engine enrichment succeeds.
 */

import { jest } from '@jest/globals';
import { HubService } from './hub.service.js';
import { RealRetrievalAdapter } from './adapters/retrieval.adapter.js';
import { RealGemmaAdapter } from './adapters/gemma.adapter.js';
import type { HubEvidenceItem } from './models/hub-evidence.model.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SAMPLE_EVIDENCE: HubEvidenceItem[] = [
  {
    file: 'src/auth/auth.service.ts',
    symbol: 'AuthService.login',
    startLine: 10,
    endLine: 20,
    score: 0.9,
    code: 'async login(user: string, pass: string) { return user === pass; }',
  },
];

function makeService(
  retrievalOverrides: Partial<RealRetrievalAdapter> = {},
  gemmaOverrides: Partial<RealGemmaAdapter> = {},
): HubService {
  const retrieval = {
    retrieve: jest.fn<() => Promise<HubEvidenceItem[]>>().mockResolvedValue(SAMPLE_EVIDENCE),
    enrichViaAiEngine: jest
      .fn<() => Promise<string | null>>()
      .mockResolvedValue('Enriched summary from AI Engine.'),
    ...retrievalOverrides,
  } as unknown as RealRetrievalAdapter;

  const gemma = {
    generateAnswer: jest.fn<() => Promise<any>>().mockResolvedValue({
      answer: 'Login validates credentials against the stored hash.',
      evidence: SAMPLE_EVIDENCE,
      confidence: 'CONFIRMED',
    }),
    debugIssue: jest.fn<() => Promise<any>>().mockResolvedValue({
      rootCause: 'The password field name is incorrect.',
      fix: 'Fix: change passwordHash to hashedPassword on line 14.',
      evidence: SAMPLE_EVIDENCE,
      confidence: 'INFERRED',
    }),
    ...gemmaOverrides,
  } as unknown as RealGemmaAdapter;

  return new HubService(retrieval, gemma);
}

// ---------------------------------------------------------------------------
// /ask
// ---------------------------------------------------------------------------

describe('HubService.ask', () => {
  it('returns a non-empty answer with evidence', async () => {
    const service = makeService();
    const result = await service.ask('How does login work?', '/some/repo');

    expect(result.answer).toBeTruthy();
    expect(result.answer.length).toBeGreaterThan(0);
    expect(result.answer).not.toBe('Insufficient evidence');
    expect(result.evidence).toHaveLength(SAMPLE_EVIDENCE.length);
    expect(result.evidence[0].code).toBeDefined();
  });

  it('populates enrichedSummary when AI Engine enrichment succeeds', async () => {
    const service = makeService();
    const result = await service.ask('How does login work?', '/some/repo');

    expect(result.enrichedSummary).toBe('Enriched summary from AI Engine.');
  });

  it('enrichedSummary is null when enrichment fails', async () => {
    const service = makeService({
      enrichViaAiEngine: jest
        .fn<() => Promise<string | null>>()
        .mockRejectedValue(new Error('AI Engine unreachable')),
    });
    const result = await service.ask('How does login work?', '/some/repo');

    // Error is swallowed — main answer still returned
    expect(result.answer).toBeTruthy();
    expect(result.enrichedSummary).toBeNull();
  });

  it('passes the question to retrieval with the repository path', async () => {
    const retrieveMock = jest
      .fn<() => Promise<HubEvidenceItem[]>>()
      .mockResolvedValue(SAMPLE_EVIDENCE);

    const service = makeService({ retrieve: retrieveMock });
    await service.ask('How does login work?', '/my/repo');

    expect(retrieveMock).toHaveBeenCalledWith('/my/repo', 'How does login work?');
  });
});

// ---------------------------------------------------------------------------
// /debug
// ---------------------------------------------------------------------------

describe('HubService.debug', () => {
  it('returns non-empty rootCause and fix with evidence', async () => {
    const service = makeService();
    const result = await service.debug('Login returns 401', '/some/repo');

    expect(result.rootCause).toBeTruthy();
    expect(result.rootCause.length).toBeGreaterThan(0);
    expect(result.fix).toBeTruthy();
    expect(result.fix.length).toBeGreaterThan(0);
    expect(result.evidence).toHaveLength(SAMPLE_EVIDENCE.length);
  });

  it('populates enrichedSummary when AI Engine enrichment succeeds', async () => {
    const service = makeService();
    const result = await service.debug('Login returns 401', '/some/repo');

    expect(result.enrichedSummary).toBe('Enriched summary from AI Engine.');
  });

  it('passes the issue to retrieval with the repository path', async () => {
    const retrieveMock = jest
      .fn<() => Promise<HubEvidenceItem[]>>()
      .mockResolvedValue(SAMPLE_EVIDENCE);

    const service = makeService({ retrieve: retrieveMock });
    await service.debug('Login returns 401', '/my/repo');

    expect(retrieveMock).toHaveBeenCalledWith('/my/repo', 'Login returns 401');
  });
});
