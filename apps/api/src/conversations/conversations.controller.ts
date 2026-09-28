import { Controller } from '@nestjs/common';
import { ConversationsService } from './conversations.service.js';

@Controller('conversations')
export class ConversationsController {
  constructor(private readonly conversationsService: ConversationsService) {}
}
