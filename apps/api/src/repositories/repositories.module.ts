import { Module } from '@nestjs/common';
import { RepositoriesController } from './repositories.controller.js';
import { RepositoriesService } from './repositories.service.js';
import { FileScannerService } from './scanner/file-scanner.service.js';

@Module({
  controllers: [RepositoriesController],
  providers: [RepositoriesService, FileScannerService],
  exports: [RepositoriesService, FileScannerService],
})
export class RepositoriesModule {}
