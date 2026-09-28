import { Controller, Get, Param } from '@nestjs/common';
import { AnalysisResult } from '../analysis/models/analysis-result.model.js';
import { FilesService } from './files.service.js';

@Controller('files')
export class FilesController {
  constructor(private readonly filesService: FilesService) {}

  @Get(':id/analysis')
  getFileAnalysis(@Param('id') id: string): Promise<AnalysisResult> {
    return this.filesService.getFileAnalysis(id);
  }
}
