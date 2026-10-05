import { IsString, IsNotEmpty } from 'class-validator';

export class GemmaRequestDto {
  @IsString()
  @IsNotEmpty()
  prompt: string;
}