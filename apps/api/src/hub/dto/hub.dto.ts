import { IsString, IsNotEmpty, MaxLength } from 'class-validator';

export class IndexRepositoryDto {
  @IsString()
  @IsNotEmpty()
  @MaxLength(4096)
  repositoryPath: string;
}

export class AskDto {
  @IsString()
  @IsNotEmpty()
  @MaxLength(10_000)
  question: string;

  @IsString()
  @IsNotEmpty()
  @MaxLength(4096)
  repositoryPath: string;
}

export class DebugDto {
  @IsString()
  @IsNotEmpty()
  @MaxLength(10_000)
  issue: string;

  @IsString()
  @IsNotEmpty()
  @MaxLength(4096)
  repositoryPath: string;
}
