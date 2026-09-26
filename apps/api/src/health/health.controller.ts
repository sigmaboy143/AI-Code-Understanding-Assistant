import { Controller, Get } from '@nestjs/common';
import {
  HealthService,
  type LivenessStatus,
  type ReadinessStatus,
} from './health.service.js';

/**
 * Phase 5 operational endpoints.
 *
 * GET /health — liveness. Answers 200 while this process is up. Never depends
 *                on the AI Engine, so a downstream outage cannot cause an
 *                orchestrator to restart a perfectly healthy application.
 * GET /ready  — readiness. Answers 200 when the AI Engine reports ready, 503
 *                otherwise.
 *
 * The controller holds no business logic and never touches AiEngineClient
 * directly; it delegates to HealthService. The 503 body is produced by the
 * service throwing an HttpException, so no @Res() is required and the declared
 * return types stay honest.
 *
 * Routes stay behind the application-wide APP_PIPE registered in AppModule.
 * That pipe is inert for these GET requests (no body, no class metatype), and
 * no route-specific exception is warranted.
 */
@Controller()
export class HealthController {
  constructor(private readonly healthService: HealthService) {}

  /** GET /health — 200 while the process is alive. */
  @Get('health')
  liveness(): LivenessStatus {
    return this.healthService.liveness();
  }

  /** GET /ready — 200 when ready, 503 when the AI Engine is not. */
  @Get('ready')
  readiness(): Promise<ReadinessStatus> {
    return this.healthService.readiness();
  }
}
