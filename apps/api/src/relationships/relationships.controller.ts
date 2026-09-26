import { Controller, Get, Query } from '@nestjs/common';
import { CodeRelationship } from '../analysis/models/code-relationship.model.js';
import { RelationshipsService } from './relationships.service.js';

@Controller('relationships')
export class RelationshipsController {
  constructor(private readonly relationshipsService: RelationshipsService) {}

  @Get()
  resolveRelationships(
    @Query('filePath') filePath: string,
    @Query('language') language: string,
  ): Promise<CodeRelationship[]> {
    return this.relationshipsService.resolveRelationships(filePath, language);
  }
}
