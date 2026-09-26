export class AnalyzeCodeDto {
  language!: string;
  code!: string;
  filePath?: string;
  context?: string;
}
