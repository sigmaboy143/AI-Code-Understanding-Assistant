/**
 * Exact request body sent to POST /api/v1/code-understanding on the AI Engine.
 * Field names are as specified by Member 3's FastAPI contract.
 */
export interface AiEngineRequestContract {
  source_code: string;
  language: string;
  file_path: string | null;
  question: string | null;
  context: string | null;
  analyses: string[];
}
