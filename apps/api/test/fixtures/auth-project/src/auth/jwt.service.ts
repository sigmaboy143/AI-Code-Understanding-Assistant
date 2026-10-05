export class JwtService {
  sign(payload: Record<string, unknown>): string {
    return JSON.stringify(payload);
  }
}
