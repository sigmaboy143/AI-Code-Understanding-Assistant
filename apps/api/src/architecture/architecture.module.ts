import { Module } from '@nestjs/common';
import { ArchitectureService } from './architecture.service.js';

@Module({
  providers: [ArchitectureService],
})
export class ArchitectureModule {}
