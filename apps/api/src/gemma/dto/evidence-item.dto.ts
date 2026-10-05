import { IsArray, IsString, IsOptional, IsNumber, IsNotEmpty, ValidateNested } from 'class-validator';

export class EvidenceItem {
  @IsString()
  @IsNotEmpty()
  file!: string;

  @IsOptional()
  @IsString()
  symbol?: string;

  @IsOptional()
  @IsNumber()
  startLine?: number;

  @IsOptional()
  @IsNumber()
  endLine?: number;

  @IsString()
  @IsNotEmpty()
  code!: string;
}

export class AnalyzeRequestDto {
  @IsString()
  @IsNotEmpty()
  question!: string;

  @IsArray()
  @ValidateNested()
  evidence!: EvidenceItem[];

  @IsOptional()
  @IsArray()
  @IsString({ each: true })
  dependencyPath?: string[];
}
