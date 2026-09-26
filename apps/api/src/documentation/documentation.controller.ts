import { Controller } from '@nestjs/common';
import { DocumentationService } from './documentation.service.js';

@Controller('documentation')
export class DocumentationController {
  constructor(private readonly documentationService: DocumentationService) {}
}
