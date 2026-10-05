import { Injectable, Logger } from '@nestjs/common';
import { RealRetrievalAdapter } from './adapters/retrieval.adapter.js';
import { RealGemmaAdapter } from './adapters/gemma.adapter.js';
import type { GemmaAnswer, GemmaDebugResult } from './adapters/gemma.adapter.js';
import type { HubEvidenceItem } from './models/hub-evidence.model.js';

@Injectable()
export class HubService {
  private readonly logger = new Logger(HubService.name);

  constructor(
    private readonly retrieval: RealRetrievalAdapter,
    private readonly gemma: RealGemmaAdapter,
  ) {}

  /**
   * Index a repository so subsequent /ask and /debug calls can retrieve from it.
   *
   * The AI Engine indexes lazily on first retrieval, so this endpoint just
   * validates that the path exists and returns a confirmation.
   */
  async indexRepository(repositoryPath: string): Promise<{ indexed: boolean; path: string }> {
    // Trigger a no-op retrieval to warm the AI Engine's in-memory index.
    this.logger.log(`Indexing repository: ${repositoryPath}`);
    try {
      await this.retrieval.retrieve(repositoryPath, '__index_warmup__', 1);
    } catch {
      // Warmup failure is non-fatal; the index will be built on the first real query.
    }
    return { indexed: true, path: repositoryPath };
  }

  /**
   * Answer `question` using source-backed evidence from `repositoryPath`.
   */
  async ask(
    question: string,
    repositoryPath: string,
  ): Promise<GemmaAnswer & { enrichedSummary: string | null }> {
    this.logger.log(`/ask: "${question}" in ${repositoryPath}`);

    // ── 1. Retrieve source-backed evidence ──────────────────────────────
    const evidence: HubEvidenceItem[] = await this.retrieval.retrieve(
      repositoryPath,
      question,
    );

    // ── 2. Optional AI Engine enrichment (3-second timeout, non-blocking) ─
    let enrichedSummary: string | null = null;
    try {
      enrichedSummary = await this.retrieval.enrichViaAiEngine(evidence, question);
    } catch {
      // Enrichment is optional — failure does not block the main answer.
    }

    // ── 3. Generate the grounded Gemma answer ────────────────────────────
    const result = await this.gemma.generateAnswer(question, evidence);

    return { ...result, enrichedSummary };
  }

  /**
   * Debug `issue` using source-backed evidence from `repositoryPath`.
   */
  async debug(
    issue: string,
    repositoryPath: string,
  ): Promise<GemmaDebugResult & { enrichedSummary: string | null }> {
    this.logger.log(`/debug: "${issue}" in ${repositoryPath}`);

    // ── 1. Retrieve evidence related to the issue ────────────────────────
    const evidence: HubEvidenceItem[] = await this.retrieval.retrieve(
      repositoryPath,
      issue,
    );

    // ── 2. Optional enrichment ───────────────────────────────────────────
    let enrichedSummary: string | null = null;
    try {
      enrichedSummary = await this.retrieval.enrichViaAiEngine(evidence, issue);
    } catch {
      // Non-blocking.
    }

    // ── 3. Generate debug analysis ───────────────────────────────────────
    const result = await this.gemma.debugIssue(issue, evidence);

    return { ...result, enrichedSummary };
  }
}
