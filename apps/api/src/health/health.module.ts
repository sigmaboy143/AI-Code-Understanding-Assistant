import { Module } from '@nestjs/common';
import { AnalysisModule } from '../analysis/analysis.module.js';
import { HealthController } from './health.controller.js';
import { HealthService } from './health.service.js';

/**
 * Phase 5 health/readiness module.
 *
 * HealthService depends on AiEngineClient, which is declared and now exported
 * by AnalysisModule along with its AI_ENGINE_CONFIG. Importing that module
 * therefore supplies both, so this module declares no providers of its own
 * beyond HealthService.
 *
 * This is what keeps a single source of truth for AI Engine access. An earlier
 * draft registered AI_ENGINE_CONFIG and AiEngineClient here as well, which
 * worked only because the config factory is env-driven and the client is
 * stateless, but it duplicated the wiring and risked the two copies drifting.
 * Consuming the exported providers removes that risk entirely.
 *
 * Nothing is exported: no other module needs the health checks, and exporting
 * unused providers would widen the module's public surface for no benefit.
 */
@Module({
  imports: [AnalysisModule],
  controllers: [HealthController],
  providers: [HealthService],
})
export class HealthModule {}
