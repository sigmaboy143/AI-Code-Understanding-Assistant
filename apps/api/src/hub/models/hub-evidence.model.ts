/**
 * Evidence item model for the hub (ask/debug) flow.
 *
 * An EvidenceItem carries the metadata that identifies a source location plus
 * the actual source lines extracted from that location.  The `code` field is
 * the critical addition: without it the Gemma prompt contains only file paths
 * and line numbers, which is insufficient for a grounded answer.
 *
 * Design rules:
 * - `code` is set by RealRetrievalAdapter only after the lines are read from
 *   disk.  It is never fabricated.
 * - When a file cannot be read the item is kept (so the location is still
 *   visible) but `code` is left undefined.
 * - `file`, `symbol`, `startLine`, and `endLine` are always preserved.
 */
export interface HubEvidenceItem {
  /** Repository-relative path of the source file. */
  file: string;
  /** Optional qualified symbol name, e.g. "AuthService.login". */
  symbol?: string;
  /** 1-based first line of the evidence in the file. */
  startLine?: number;
  /** 1-based last line of the evidence in the file. */
  endLine?: number;
  /** Relevance score in [0, 1] assigned by the retriever. */
  score?: number;
  /**
   * Actual source lines extracted from startLine..endLine.
   * Set by RealRetrievalAdapter; absent when the file cannot be read.
   */
  code?: string;
}
