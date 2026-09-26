export class AnalyzeFileDto {
  language!: string;
  filePath!: string;
  code!: string;
  context?: string;
}
