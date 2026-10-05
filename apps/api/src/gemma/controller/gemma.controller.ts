import { Controller, Post, Body, HttpCode, HttpStatus } from '@nestjs/common';
import { GemmaRequestDto } from '../dto/gemma-request.dto';
import { GemmaService } from '../service/gemma.service';

@Controller()
export class GemmaController {
  constructor(private readonly gemmaService: GemmaService) {}

  /**
   * POST /ai/test
   * Tests the Gemma 4 model with a simple prompt.
   */
  @Post('ai/test')
  @HttpCode(HttpStatus.OK)
  async test(@Body() dto: GemmaRequestDto): Promise<{
    success: boolean;
    model: string;
    response: string;
  }> {
    const response = await this.gemmaService.generateResponse(dto.prompt);

    return {
      success: true,
      model: 'gemma-4-26b-a4b-it',
      response,
    };
  }
}