/**
 * Unit tests for RealGemmaAdapter
 *
 * Proves:
 * 1. generateAnswer() passes evidence with code to the AI Engine.
 * 2. debugIssue() passes evidence with code to the AI Engine.
 * 3. Both methods return non-empty grounded answers when evidence has code.
 * 4. The AI Engine receives actual source_code, not empty or stub content.
 */

import { jest } from '@jest/globals';
import { RealGemmaAdapter } from './gemma.adapter.js';
import type { HubEvidenceItem } from '../models/hub-evidence.model.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeAdapter(): RealGemmaAdapter {
  return new RealGemmaAdapter();
}

const SAMPLE_EVIDENCE: HubEvidenceItem[] = [
  {
    file: 'src/auth/auth.service.ts',
    symbol: 'AuthService.login',
    startLine: 10,
    endLine: 25,
    score: 0.9,
    code: `
  async login(username: string, password: string): Promise<User | null> {
    const user = await this.userRepo.findOne({ username });
    if (!user) return null;
    const valid = await bcrypt.compare(password, user.passwordHash);
    return valid ? user : null;
  }
    `.trim(),
  },
  {
    file: 'src/auth/auth.controller.ts',
    symbol: 'AuthController.login',
    startLine: 5,
    endLine: 12,
    score: 0.7,
    code: `
  @Post('login')
  async login(@Body() dto: LoginDto) {
    const user = await this.authService.login(dto.username, dto.password);
    if (!user) throw new UnauthorizedException();
    return this.authService.createToken(user);
  }
    `.trim(),
  },
];

// ---------------------------------------------------------------------------
// generateAnswer tests
// ---------------------------------------------------------------------------

describe('RealGemmaAdapter.generateAnswer', () => {
  it('returns a non-empty answer when evidence has code', async () => {
    (global as any).fetch = jest.fn<typeof fetch>().mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          summary:
            'The login function validates the user credentials against the hashed password in the database.',
          confidence: { level: 'CONFIRMED', evidence: [], notes: null },
        }),
    } as Response);

    const adapter = makeAdapter();
    const result = await adapter.generateAnswer(
      'How does login work?',
      SAMPLE_EVIDENCE,
    );

    expect(result.answer).toBeTruthy();
    expect(result.answer.length).toBeGreaterThan(0);
    expect(result.answer).not.toBe('Insufficient evidence');
    expect(result.confidence).toBe('CONFIRMED');
    expect(result.evidence).toBe(SAMPLE_EVIDENCE);
  });

  it('sends actual source_code to the AI Engine (not empty/stub)', async () => {
    let capturedBody: any = null;

    (global as any).fetch = jest
      .fn<typeof fetch>()
      .mockImplementation(async (_url: string, init?: RequestInit) => {
        capturedBody = JSON.parse(init?.body as string);
        return {
          ok: true,
          json: () =>
            Promise.resolve({
              summary: 'The login method checks credentials.',
              confidence: { level: 'CONFIRMED', evidence: [], notes: null },
            }),
        } as Response;
      });

    const adapter = makeAdapter();
    await adapter.generateAnswer('How does login work?', SAMPLE_EVIDENCE);

    expect(capturedBody).not.toBeNull();
    // source_code must be the real login code, not a comment stub
    expect(capturedBody.source_code).toContain('bcrypt.compare');
    expect(capturedBody.source_code).not.toMatch(/^\/\/ No source/);
    // question must be forwarded
    expect(capturedBody.question).toContain('login');
    // analysis must be set
    expect(capturedBody.analyses).toContain('explanation');
  });

  it('still calls AI Engine with fallback source when evidence has no code', async () => {
    let capturedBody: any = null;

    (global as any).fetch = jest
      .fn<typeof fetch>()
      .mockImplementation(async (_url: string, init?: RequestInit) => {
        capturedBody = JSON.parse(init?.body as string);
        return {
          ok: true,
          json: () =>
            Promise.resolve({
              summary: 'Insufficient evidence to determine login behavior.',
            }),
        } as Response;
      });

    const adapter = makeAdapter();
    const evidenceWithoutCode: HubEvidenceItem[] = [
      { file: 'auth.ts', symbol: 'login', score: 0.5 },
    ];

    const result = await adapter.generateAnswer(
      'How does login work?',
      evidenceWithoutCode,
    );

    // The call still goes through (model can say "insufficient evidence")
    expect(capturedBody).not.toBeNull();
    // source_code is a non-empty placeholder
    expect(capturedBody.source_code.length).toBeGreaterThan(0);
    // answer is whatever the model returned
    expect(result.answer).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// debugIssue tests
// ---------------------------------------------------------------------------

describe('RealGemmaAdapter.debugIssue', () => {
  it('returns non-empty rootCause and fix when evidence has code', async () => {
    (global as any).fetch = jest.fn<typeof fetch>().mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          summary:
            'The login route returns 401 because the password comparison uses the wrong hash field.\n\nFix: Change `user.passwordHash` to `user.hashedPassword` on line 14.',
          confidence: { level: 'INFERRED', evidence: [], notes: null },
        }),
    } as Response);

    const adapter = makeAdapter();
    const result = await adapter.debugIssue(
      'Login returns 401',
      SAMPLE_EVIDENCE,
    );

    expect(result.rootCause).toBeTruthy();
    expect(result.rootCause.length).toBeGreaterThan(0);
    expect(result.fix).toBeTruthy();
    expect(result.fix.length).toBeGreaterThan(0);
    expect(result.confidence).toBe('INFERRED');
  });

  it('sends actual source_code and error_explanation analysis to the AI Engine', async () => {
    let capturedBody: any = null;

    (global as any).fetch = jest
      .fn<typeof fetch>()
      .mockImplementation(async (_url: string, init?: RequestInit) => {
        capturedBody = JSON.parse(init?.body as string);
        return {
          ok: true,
          json: () =>
            Promise.resolve({
              summary: 'Root cause: wrong field name. Fix: use hashedPassword.',
              confidence: { level: 'INFERRED', evidence: [], notes: null },
            }),
        } as Response;
      });

    const adapter = makeAdapter();
    await adapter.debugIssue('Login returns 401', SAMPLE_EVIDENCE);

    expect(capturedBody).not.toBeNull();
    // Actual source code sent
    expect(capturedBody.source_code).toContain('bcrypt.compare');
    // error_explanation analysis used for debugging
    expect(capturedBody.analyses).toContain('error_explanation');
    // Issue embedded in question
    expect(capturedBody.question).toContain('Login returns 401');
  });

  it('evidence is attached to the returned result', async () => {
    (global as any).fetch = jest.fn<typeof fetch>().mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          summary: 'Root cause found. Fix: update the hash field.',
        }),
    } as Response);

    const adapter = makeAdapter();
    const result = await adapter.debugIssue('Login returns 401', SAMPLE_EVIDENCE);

    expect(result.evidence).toBe(SAMPLE_EVIDENCE);
  });
});
