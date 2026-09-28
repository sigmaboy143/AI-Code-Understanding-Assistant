import { Body, Controller, Post } from '@nestjs/common';
import { ExplainCodeDto } from './dto/explain-code.dto.js';
import { ExplanationResponseDto } from './dto/explanation-response.dto.js';
import { ExplanationsService } from './explanations.service.js';

@Controller('explanations')
export class ExplanationsController {
  constructor(private readonly explanationsService: ExplanationsService) {}

  @Post()
  explain(@Body() dto: ExplainCodeDto): Promise<ExplanationResponseDto> {
    return this.explanationsService.explain(dto);
  }
}
