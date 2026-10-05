import { IsString, Matches } from 'class-validator';

export class IndexRepositoryDto {
  @IsString()
  @Matches(/\S/, { message: 'repositoryPath must not be blank' })
  repositoryPath!: string;
}
