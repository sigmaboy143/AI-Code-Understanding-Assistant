import { Controller } from '@nestjs/common';
import { OnboardingService } from './onboarding.service.js';

@Controller('onboarding')
export class OnboardingController {
  constructor(private readonly onboardingService: OnboardingService) {}
}
