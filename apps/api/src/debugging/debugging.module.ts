import { Module } from '@nestjs/common';
import { DebuggingService } from './debugging.service.js';

@Module({
  providers: [DebuggingService],
})
export class DebuggingModule {}
