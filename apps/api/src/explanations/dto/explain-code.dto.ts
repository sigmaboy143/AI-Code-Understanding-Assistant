import { Allow } from 'class-validator';

export class ExplainCodeDto {
  // @Allow() is whitelist preservation only. It contributes no validation
  // constraint of any kind. It is required on every property here because the
  // application-wide pipe runs with `whitelist: true`, which strips any request
  // property that carries no validation metadata. Without it, `language`, `code`
  // and `filePath` would be silently deleted before the controller body runs.
  @Allow()
  language!: string;

  @Allow()
  code!: string;

  @Allow()
  filePath?: string;

  @Allow()
  startLine?: number;

  @Allow()
  endLine?: number;

  @Allow()
  detailLevel?: 'brief' | 'standard' | 'detailed';
}
