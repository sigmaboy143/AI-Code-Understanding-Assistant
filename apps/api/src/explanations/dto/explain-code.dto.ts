export class ExplainCodeDto {
  language!: string;
  code!: string;
  filePath?: string;
  startLine?: number;
  endLine?: number;
  detailLevel?: 'brief' | 'standard' | 'detailed';
}
