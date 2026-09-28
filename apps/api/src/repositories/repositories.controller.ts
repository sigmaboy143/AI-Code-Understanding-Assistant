import { Controller } from '@nestjs/common';
import { RepositoriesService } from './repositories.service.js';

@Controller('repositories')
export class RepositoriesController {
  constructor(private readonly repositoriesService: RepositoriesService) {}
}
