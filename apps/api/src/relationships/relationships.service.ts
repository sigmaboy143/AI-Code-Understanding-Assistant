import { Injectable } from '@nestjs/common';
import { promises as fs } from 'fs';
import { CodeRelationship } from '../analysis/models/code-relationship.model.js';
import { RelationshipExtractorService } from '../code-intelligence/extractor/relationship-extractor.service.js';

const SUPPORTED_EXTENSIONS = new Set(['.ts', '.tsx', '.js', '.jsx']);

function extensionFor(filePath: string, language: string): string {
  const dotIdx = filePath.lastIndexOf('.');
  if (dotIdx >= 0) {
    const ext = filePath.slice(dotIdx).toLowerCase();
    if (SUPPORTED_EXTENSIONS.has(ext)) return ext;
  }
  switch (language.toLowerCase()) {
    case 'typescript':
    case 'ts':
      return '.ts';
    case 'tsx':
      return '.tsx';
    case 'javascript':
    case 'js':
      return '.js';
    case 'jsx':
      return '.jsx';
    default:
      return '.ts';
  }
}

@Injectable()
export class RelationshipsService {
  constructor(
    private readonly relationshipExtractor: RelationshipExtractorService,
  ) {}

  /**
   * Reads a source file from disk and extracts its relationships (imports,
   * extends, implements, contains, local calls). Returns an empty array when
   * the file cannot be read or its extension is unsupported.
   */
  async resolveRelationships(
    filePath: string,
    language: string,
  ): Promise<CodeRelationship[]> {
    let source: string;
    try {
      source = await fs.readFile(filePath, 'utf8');
    } catch {
      return [];
    }
    return this.relationshipExtractor.extractFromSource(
      source,
      filePath,
      extensionFor(filePath, language),
    );
  }
}
