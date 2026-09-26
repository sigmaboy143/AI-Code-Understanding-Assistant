import { Module } from '@nestjs/common';
import { ImpactService } from './impact.service.js';

@Module({
  providers: [ImpactService],
})
export class ImpactModule {}
