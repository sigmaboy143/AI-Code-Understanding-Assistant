import { Controller } from '@nestjs/common';
import { TestsService } from './tests.service.js';

@Controller('tests')
export class TestsController {
  constructor(private readonly testsService: TestsService) {}
}
