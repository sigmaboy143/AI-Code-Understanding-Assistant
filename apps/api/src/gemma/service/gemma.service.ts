import { Injectable, Logger, BadGatewayException } from '@nestjs/common';
import { GoogleGenAI } from '@google/genai';
import { GemmaRequestDto } from '../dto/gemma-request.dto';
import { AnalyzeRequestDto, EvidenceItem } from '../dto/evidence-item.dto';

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

  async analyzeWithEvidence(
    question: string,
    evidence: EvidenceItem[],
    dependencyPath?: string[]
  ): Promise<{
    answer: string;
    confidence: 'high' | 'medium' | 'low';
    insufficientEvidence: boolean;
  }> {
    // Build the evidence section of the prompt
    const evidenceSections = evidence.map((item, idx) => {
      const header = `[Evidence ${idx + 1}: ${item.file}]`;
      const symbolInfo = item.symbol ? ` — Symbol: ${item.symbol}` : '';
      const lineInfo = item.startLine !== undefined || item.endLine !== undefined
        ? ` (lines ${item.startLine ?? ''}${item.endLine !== undefined ? `-${item.endLine}` : ''})`
        : '';
      const codeBlock = item.code.replace(/\n/g, '\n      ');
      return `${header}${symbolInfo}${lineInfo}\n      \`\`\`${codeBlock}\`\`\``;
    });

    const evidenceText = evidenceSections.length > 0 ? evidenceSections.join('\n\n') : 'No evidence provided.';

    // Construct the prompt that enforces evidence-grounded responses
    const prompt = `You are an evidence-grounded code understanding assistant. Your task is to answer the user's question about code using ONLY the supplied evidence below.

CRITICAL RULES:
1. Answer ONLY from the supplied evidence. Never invent a file, function, class, symbol, dependency, or behavior.
2. Every important claim must be grounded in the supplied evidence. If a claim is not supported by the evidence, explicitly say so.
3. If the evidence directly supports a limited, grounded explanation, you MUST provide that explanation rather than defaulting to "Insufficient evidence". Provide the grounded partial answer based on the evidence. Only say "Insufficient evidence" when the evidence cannot answer any meaningful part of the question.
4. If the evidence is genuinely insufficient to answer the question, explicitly say: "Insufficient evidence"
5. Never pretend missing evidence exists.
6. Treat the dependencyPath as supporting context only — it does NOT give you permission to invent details not present in the evidence.
7. Keep the answer concise but technically useful.
8. Return a confidence rating: "high", "medium", or "low" based on how well the evidence supports your answer.

DEPENDENCY PATH (supporting context only, do not invent from this):
${dependencyPath ? dependencyPath.map(d => `- ${d}`).join('\n') : 'None provided'}

QUESTION:
${question}

EVIDENCE:
${evidenceText}

ANSWER (provide your answer below, followed by the confidence rating in brackets, e.g., [high]):`;
    
    const response = await this.generateResponse(prompt);

    // Determine if the model indicates insufficient evidence
    const hasInsufficientEvidence = response.toLowerCase().includes('insufficient evidence');

    // Parse confidence from [high|medium|low] bracket
    const confidenceMatch = response.match(/\[(high|medium|low)\]/i);
    const modelConfidence: 'high' | 'medium' | 'low' | null = confidenceMatch
      ? confidenceMatch[1].toLowerCase() as 'high' | 'medium' | 'low'
      : null;

    let insufficientEvidence: boolean;
    let confidence: 'high' | 'medium' | 'low';

    // Rule: If the model returns text indicating insufficient evidence, normalize
    if (hasInsufficientEvidence) {
      insufficientEvidence = true;
      confidence = 'low';
    } else {
      // Grounded answer exists
      insufficientEvidence = false;

      // Use model's confidence if available; otherwise default to medium
      // since the model chose to answer rather than say "Insufficient evidence"
      if (modelConfidence) {
        confidence = modelConfidence;
      } else {
        confidence = 'medium';
      }
    }

    // Do NOT allow a model-produced confidence label to override deterministic consistency rule.
    // If insufficientEvidence is true, confidence MUST be "low" (already enforced above).
    // If insufficientEvidence is false, the model's confidence choice stands (high/medium/low based on evidence strength).

    // Format the answer and extract the confidence bracket if present
    let answer = response;
    if (insufficientEvidence) {
      answer = 'Insufficient evidence to determine this reliably.';
    } else {
      // Remove the confidence bracket from the answer if present
      answer = response.replace(/\[(high|medium|low)\]/i, '').trim();
    }

    return { answer, confidence, insufficientEvidence };
  }
}