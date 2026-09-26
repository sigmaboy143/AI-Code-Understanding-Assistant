import { Controller } from '@nestjs/common';
import { ExplanationsService } from './explanations.service.js';

@Controller('explanations')
export class ExplanationsController {
  constructor(private readonly explanationsService: ExplanationsService) {}
}
