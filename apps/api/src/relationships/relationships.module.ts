import { Module } from '@nestjs/common';
import { RelationshipsController } from './relationships.controller.js';
import { RelationshipsService } from './relationships.service.js';
import { CodeIntelligenceModule } from '../code-intelligence/code-intelligence.module.js';

@Module({
  imports: [CodeIntelligenceModule],
  controllers: [RelationshipsController],
  providers: [RelationshipsService],
})
export class RelationshipsModule {}
