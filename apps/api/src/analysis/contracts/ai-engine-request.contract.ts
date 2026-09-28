/**
 * Exact request body sent to POST /api/v1/code-understanding on the AI Engine.
 * Field names are as specified by Member 3's FastAPI contract
 * (feature/member3-ai @ 532f035, app/schemas/code_understanding.py).
 */

/**
 * Exact `AnalysisType` values of the AI Engine's `CodeUnderstandingRequest`.
 *
 * The AI Engine validates this field against its own enum, so any value outside
 * this set is rejected with 422 VALIDATION_ERROR.
 */
export type AiEngineAnalysisType =
  | 'explanation'
  | 'error_explanation'
  | 'structure'
  | 'dependencies'
  | 'improvements';

export interface AiEngineRequestContract {
  source_code: string;
  language: string;
  file_path: string | null;
  question: string | null;
  context: string | null;
  /**
   * Optional, and omitted entirely when NestJS has no explicit selection.
   *
   * `CodeUnderstandingRequest.analyses` is `list[AnalysisType]` with
   * `min_length=1` and `default_factory=list(AnalysisType)`. Consequences:
   *
   * - An empty array violates `min_length=1` and is rejected with 422. It must
   *   therefore never be sent.
   * - Omitting the field is valid: the AI Engine then applies its own default
   *   of all five analysis types, which is the correct behaviour for a caller
   *   that has no explicit per-request selection.
   *
   * `JSON.stringify` drops `undefined` properties, so assigning `undefined`
   * omits the key from the serialised body entirely.
   */
  analyses?: AiEngineAnalysisType[];
}
