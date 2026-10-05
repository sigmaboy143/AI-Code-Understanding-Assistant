import { Injectable, Logger, BadGatewayException } from '@nestjs/common';
import { GoogleGenAI } from '@google/genai';
import { GemmaRequestDto } from '../dto/gemma-request.dto';

const MODEL_NAME = 'gemma-4-26b-a4b-it';

@Injectable()
export class GemmaService {
  private readonly logger = new Logger(GemmaService.name);
  private readonly client: GoogleGenAI | null = null;

  constructor() {
    const apiKey = process.env['GEMINI_API_KEY'];

    if (!apiKey) {
      this.logger.warn('GEMINI_API_KEY not set; Gemma service will return fallback responses');
      this.client = null;
    } else {
      try {
        this.client = new GoogleGenAI({ apiKey });
        this.logger.log(`Gemma client initialized with model ${MODEL_NAME}`);
      } catch (err) {
        this.logger.error(`Failed to initialize Gemma client: ${err}`);
        this.client = null;
      }
    }
  }

  async generateResponse(prompt: string): Promise<string> {
    if (!prompt || prompt.trim().length === 0) {
      return 'Please provide a non-empty prompt.';
    }

    // If no API key or client failed to initialize, return fallback
    if (!this.client) {
      return `Gemma service is available (model: ${MODEL_NAME}) but no GEMINI_API_KEY is configured. ` +
        `Set the GEMINI_API_KEY environment variable to enable AI responses. ` +
        `Your prompt: "${prompt}"`;
    }

    try {
      const result = await this.client.models.generateContent({
        model: MODEL_NAME,
        contents: prompt,
      });

      if (result?.text) {
        return result.text;
      }

      return 'No response generated from Gemma model.';
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : String(err);
      this.logger.error(`Gemma API error: ${errorMessage}`);

      // Handle specific error cases
      if (errorMessage.includes('401') || errorMessage.includes('unauthenticated') || errorMessage.includes('API key')) {
        return 'Gemma service: invalid or missing API key. Please configure GEMINI_API_KEY.';
      }

      if (errorMessage.includes('429') || errorMessage.includes('rate limit') || errorMessage.includes('quota')) {
        return 'Gemma service: rate limit exceeded. Please try again shortly.';
      }

      if (errorMessage.includes('400') || errorMessage.includes('bad request')) {
        return 'Gemma service: bad request. Please check your prompt and try again.';
      }

      return `Gemma service error: ${errorMessage}`;
    }
  }
}