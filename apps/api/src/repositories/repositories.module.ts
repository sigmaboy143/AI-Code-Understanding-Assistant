import { Module } from '@nestjs/common';
import { RepositoriesController } from './repositories.controller.js';
import { RepositoriesService } from './repositories.service.js';

@Module({
  controllers: [RepositoriesController],
  providers: [RepositoriesService],
})
export class RepositoriesModule {}
