import { Controller } from '@nestjs/common';
import { FilesService } from './files.service.js';

@Controller('files')
export class FilesController {
  constructor(private readonly filesService: FilesService) {}
}
