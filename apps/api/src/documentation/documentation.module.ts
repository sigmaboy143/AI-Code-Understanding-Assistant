import { Module } from '@nestjs/common';
import { DocumentationController } from './documentation.controller.js';
import { DocumentationService } from './documentation.service.js';

@Module({
  controllers: [DocumentationController],
  providers: [DocumentationService],
})
export class DocumentationModule {}
