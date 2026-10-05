import { Module } from '@nestjs/common';
import { APP_PIPE } from '@nestjs/core';
import { AppController } from './app.controller.js';
import { AppService } from './app.service.js';
import { AuthModule } from './auth/auth.module.js';
import { UsersModule } from './users/users.module.js';
import { OrganizationsModule } from './organizations/organizations.module.js';
import { ProjectsModule } from './projects/projects.module.js';
import { RepositoriesModule } from './repositories/repositories.module.js';
import { FilesModule } from './files/files.module.js';
import { SymbolsModule } from './symbols/symbols.module.js';
import { RelationshipsModule } from './relationships/relationships.module.js';
import { AnalysisModule } from './analysis/analysis.module.js';
import { GitModule } from './git/git.module.js';
import { ImpactModule } from './impact/impact.module.js';
import { DebuggingModule } from './debugging/debugging.module.js';
import { ArchitectureModule } from './architecture/architecture.module.js';
import { DocumentationModule } from './documentation/documentation.module.js';
import { TestsModule } from './tests/tests.module.js';
import { ExplanationsModule } from './explanations/explanations.module.js';
import { ConversationsModule } from './conversations/conversations.module.js';
import { OnboardingModule } from './onboarding/onboarding.module.js';
import { HealthModule } from './health/health.module.js';
import { CommonModule } from './common/common.module.js';
import { CodeIntelligenceModule } from './code-intelligence/code-intelligence.module.js';
import { createValidationPipe } from './common/validation/validation-pipe.js';

@Module({
  imports: [
    // Registered once, at the root. CommonModule owns the correlation
    // middleware configuration and is the single source of LOG_SINK/AppLogger;
    // feature modules import it themselves rather than re-providing either.
    CommonModule,
    AuthModule,
    UsersModule,
    OrganizationsModule,
    ProjectsModule,
    RepositoriesModule,
    FilesModule,
    SymbolsModule,
    RelationshipsModule,
    AnalysisModule,
    GitModule,
    ImpactModule,
    DebuggingModule,
    ArchitectureModule,
    DocumentationModule,
    TestsModule,
    ExplanationsModule,
    ConversationsModule,
    OnboardingModule,
    HealthModule,
    CodeIntelligenceModule,
  ],
  controllers: [AppController],
  providers: [
    AppService,
    // Application-wide validation. Registering the pipe as an APP_PIPE provider
    // keeps the options in one place: createValidationPipe() is the single
    // source of truth for them, so they can never drift from
    // validation-pipe.ts or be redefined per-controller. Prefer this over
    // useGlobalPipes() in main.ts, which would leave the pipe untestable and
    // invisible to module-scoped Test.createTestingModule() harnesses.
    {
      provide: APP_PIPE,
      useFactory: createValidationPipe,
    },
  ],
})
export class AppModule {}
