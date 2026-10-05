import { jest } from '@jest/globals';
import { GemmaAdapter } from './gemma.adapter.js';
import { GemmaService } from './service/gemma.service.js';
import type { LLMResponse, RetrievalContext } from './gemma-adapter.interface.js';

// ─── Shared fixtures ────────────────────────────────────────────────────────

const EVIDENCE_ITEM = {
  file: 'src/auth/auth.controller.ts',
  symbol: 'AuthController.login',
  startLine: 10,
  endLine: 20,
  code: 'async login() { return this.authService.validateUser(); }',
};

const CONTEXT_WITH_EVIDENCE: RetrievalContext = {
  evidence: [EVIDENCE_ITEM],
  dependencyPath: ['AuthController.login', 'AuthService.validateUser', 'JwtService.sign'],
};

const CONTEXT_EMPTY: RetrievalContext = {
  evidence: [],
  dependencyPath: [],
};

// ─── Helper to create the adapter with a mocked GemmaService ────────────────

function makeAdapter(
  analyzeOverride?: Partial<{ answer: string; confidence: 'high' | 'medium' | 'low'; insufficientEvidence: boolean }>,
) {
  const defaultResult = {
    answer: 'The login flow calls AuthService.validateUser then JwtService.sign. [high]',
    confidence: 'high' as const,
    insufficientEvidence: false,
  };

  const mockGemmaService = {
    analyzeWithEvidence: jest.fn().mockResolvedValue({
      ...defaultResult,
      ...analyzeOverride,
    }),
    generateResponse: jest.fn().mockResolvedValue('mock response'),
  };

  const adapter = new GemmaAdapter(mockGemmaService as unknown as GemmaService);
  return { adapter, mockGemmaService };
}

// ─── Test suite ─────────────────────────────────────────────────────────────

describe('GemmaAdapter', () => {
  // 1. generateAnswer() success ──────────────────────────────────────────────
  describe('generateAnswer()', () => {
    it('returns an LLMResponse with answer populated', async () => {
      const { adapter } = makeAdapter();
      const result = await adapter.generateAnswer('How does login work?', CONTEXT_WITH_EVIDENCE);

      expect(result).toBeDefined();
      expect(typeof result.answer).toBe('string');
      expect(result.answer.length).toBeGreaterThan(0);
    });

    // 3. evidence mapping ────────────────────────────────────────────────────
    it('maps supplied evidence to LLMResponse evidence', async () => {
      const { adapter } = makeAdapter();
      const result = await adapter.generateAnswer('How does login work?', CONTEXT_WITH_EVIDENCE);

      expect(result.evidence).toBeDefined();
      expect(result.evidence!.length).toBe(1);
      expect(result.evidence![0].file).toBe(EVIDENCE_ITEM.file);
      expect(result.evidence![0].symbol).toBe(EVIDENCE_ITEM.symbol);
      expect(result.evidence![0].startLine).toBe(EVIDENCE_ITEM.startLine);
      expect(result.evidence![0].endLine).toBe(EVIDENCE_ITEM.endLine);
    });

    // 4. dependencyPath mapping ──────────────────────────────────────────────
    it('preserves dependencyPath from context', async () => {
      const { adapter } = makeAdapter();
      const result = await adapter.generateAnswer('How does login work?', CONTEXT_WITH_EVIDENCE);

      expect(result.dependencyPath).toEqual(CONTEXT_WITH_EVIDENCE.dependencyPath);
    });

    it('omits dependencyPath when context has none', async () => {
      const { adapter } = makeAdapter();
      const result = await adapter.generateAnswer('query', CONTEXT_EMPTY);

      expect(result.dependencyPath).toBeUndefined();
    });

    it('passes question and evidence to GemmaService.analyzeWithEvidence', async () => {
      const { adapter, mockGemmaService } = makeAdapter();
      await adapter.generateAnswer('How does login work?', CONTEXT_WITH_EVIDENCE);

      expect(mockGemmaService.analyzeWithEvidence).toHaveBeenCalledWith(
        'How does login work?',
        expect.arrayContaining([
          expect.objectContaining({ file: EVIDENCE_ITEM.file }),
        ]),
        CONTEXT_WITH_EVIDENCE.dependencyPath,
      );
    });

    // 8. insufficient evidence ───────────────────────────────────────────────
    it('handles insufficient evidence gracefully', async () => {
      const { adapter } = makeAdapter({
        answer: 'Insufficient evidence to determine this reliably.',
        confidence: 'low',
        insufficientEvidence: true,
      });
      const result = await adapter.generateAnswer('unknown question', CONTEXT_EMPTY);

      expect(result.answer).toBeTruthy();
      // No rootCause/fix should be added for generateAnswer
      expect(result.rootCause).toBeUndefined();
      expect(result.fix).toBeUndefined();
    });

    // 9. Gemma/API failure ───────────────────────────────────────────────────
    it('propagates errors from GemmaService', async () => {
      const mockGemmaService = {
        analyzeWithEvidence: jest.fn().mockRejectedValue(new Error('API error')),
      };
      const adapter = new GemmaAdapter(mockGemmaService as unknown as GemmaService);

      await expect(adapter.generateAnswer('query', CONTEXT_EMPTY)).rejects.toThrow('API error');
    });
  });

  // 2. debugIssue() success ──────────────────────────────────────────────────
  describe('debugIssue()', () => {
    const debugAnswer = [
      'ROOT_CAUSE: NullPointerException in AuthService.validateUser at line 15',
      'SUGGESTED_FIX: Add a null-check before accessing user.id',
      'EXPLANATION: The evidence shows validateUser can return null when the user is not found. [high]',
    ].join('\n');

    it('returns an LLMResponse with answer populated', async () => {
      const { adapter } = makeAdapter({ answer: debugAnswer });
      const result = await adapter.debugIssue('login throws NullPointerException', CONTEXT_WITH_EVIDENCE);

      expect(result.answer).toBeTruthy();
    });

    // 5. rootCause mapping ───────────────────────────────────────────────────
    it('extracts rootCause from structured Gemma response', async () => {
      const { adapter } = makeAdapter({ answer: debugAnswer });
      const result = await adapter.debugIssue('login throws NullPointerException', CONTEXT_WITH_EVIDENCE);

      expect(result.rootCause).toContain('NullPointerException');
    });

    // 6 & 7. fix / suggestedFix → fix mapping ────────────────────────────────
    it('maps SUGGESTED_FIX → public field "fix"', async () => {
      const { adapter } = makeAdapter({ answer: debugAnswer });
      const result = await adapter.debugIssue('login throws NullPointerException', CONTEXT_WITH_EVIDENCE);

      expect(result.fix).toContain('null-check');
    });

    it('does not expose suggestedFix (only fix)', async () => {
      const { adapter } = makeAdapter({ answer: debugAnswer });
      const result = (await adapter.debugIssue('issue', CONTEXT_WITH_EVIDENCE)) as any;

      expect(result.suggestedFix).toBeUndefined();
    });

    // 3. evidence mapping ────────────────────────────────────────────────────
    it('includes evidence in debug response', async () => {
      const { adapter } = makeAdapter({ answer: debugAnswer });
      const result = await adapter.debugIssue('issue', CONTEXT_WITH_EVIDENCE);

      expect(result.evidence).toBeDefined();
      expect(result.evidence![0].file).toBe(EVIDENCE_ITEM.file);
    });

    // 4. dependencyPath mapping ──────────────────────────────────────────────
    it('preserves dependencyPath in debug response', async () => {
      const { adapter } = makeAdapter({ answer: debugAnswer });
      const result = await adapter.debugIssue('issue', CONTEXT_WITH_EVIDENCE);

      expect(result.dependencyPath).toEqual(CONTEXT_WITH_EVIDENCE.dependencyPath);
    });

    // 8. insufficient evidence for debug ────────────────────────────────────
    it('omits rootCause and fix when evidence is insufficient', async () => {
      const { adapter } = makeAdapter({
        answer: 'Insufficient evidence to determine this reliably.',
        confidence: 'low',
        insufficientEvidence: true,
      });
      const result = await adapter.debugIssue('null pointer', CONTEXT_EMPTY);

      expect(result.rootCause).toBeUndefined();
      expect(result.fix).toBeUndefined();
      expect(result.answer).toBeTruthy();
    });

    it('omits rootCause when model returns "Cannot determine from evidence"', async () => {
      const { adapter } = makeAdapter({
        answer: [
          'ROOT_CAUSE: Cannot determine from evidence',
          'SUGGESTED_FIX: Cannot determine from evidence',
          'EXPLANATION: Not enough context.',
        ].join('\n'),
        insufficientEvidence: false,
        confidence: 'low',
      });
      const result = await adapter.debugIssue('issue', CONTEXT_WITH_EVIDENCE);

      expect(result.rootCause).toBeUndefined();
      expect(result.fix).toBeUndefined();
    });

    // 9. Gemma/API failure ───────────────────────────────────────────────────
    it('propagates errors from GemmaService in debugIssue', async () => {
      const mockGemmaService = {
        analyzeWithEvidence: jest.fn().mockRejectedValue(new Error('Network error')),
      };
      const adapter = new GemmaAdapter(mockGemmaService as unknown as GemmaService);

      await expect(adapter.debugIssue('issue', CONTEXT_EMPTY)).rejects.toThrow('Network error');
    });
  });

  // 10. AdapterService.setGemmaAdapter compatibility ────────────────────────
  describe('AdapterService compatibility', () => {
    it('can be substituted into an IGemmaAdapter slot (structural check)', () => {
      const { adapter } = makeAdapter();

      // Verify the adapter exposes the exact methods Prakash's AdapterService expects
      expect(typeof adapter.generateAnswer).toBe('function');
      expect(typeof adapter.debugIssue).toBe('function');
    });

    it('satisfies setGemmaAdapter(adapter) signature', () => {
      // Simulate what Prakash's AdapterService.setGemmaAdapter does
      const registry: { gemma: { generateAnswer: Function; debugIssue: Function } | null } = { gemma: null };
      const setGemmaAdapter = (a: { generateAnswer: Function; debugIssue: Function }) => {
        registry.gemma = a;
      };

      const { adapter } = makeAdapter();
      setGemmaAdapter(adapter);

      expect(registry.gemma).toBe(adapter);
    });
  });
});
