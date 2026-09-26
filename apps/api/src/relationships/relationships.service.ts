import { Injectable } from '@nestjs/common';
import { CodeRelationship } from '../analysis/models/code-relationship.model.js';

@Injectable()
export class RelationshipsService {
  resolveRelationships(
    _filePath: string,
    _language: string,
  ): Promise<CodeRelationship[]> {
    return Promise.resolve([]);
  }
}
