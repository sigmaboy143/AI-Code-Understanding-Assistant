import { IsOptional, IsString, Matches, MaxLength } from 'class-validator';

export class AnalyzeCodeDto {
  @IsString()
  @Matches(/\S/, { message: 'language must not be blank' })
  language!: string;

  @IsString()
  @Matches(/\S/, { message: 'code must not be blank' })
  @MaxLength(100000, {
    message: 'code must not exceed 100000 characters',
  })
  code!: string;

  @IsOptional()
  @IsString()
  filePath?: string;

  @IsOptional()
  @IsString()
  context?: string;
}
