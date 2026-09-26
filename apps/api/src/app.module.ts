import { Module } from '@nestjs/common';
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

@Module({
  imports: [
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
  ],
  controllers: [AppController],
  providers: [AppService],
})
export class AppModule {}
