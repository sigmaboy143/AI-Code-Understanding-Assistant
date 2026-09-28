import { Module } from '@nestjs/common';
import { RelationshipsController } from './relationships.controller.js';
import { RelationshipsService } from './relationships.service.js';

@Module({
  controllers: [RelationshipsController],
  providers: [RelationshipsService],
})
export class RelationshipsModule {}
