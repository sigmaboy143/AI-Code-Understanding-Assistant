import { AuthService } from './auth.service.js';

export class AuthController {
  constructor(private readonly authService: AuthService) {}

  login(email: string): Promise<string> {
    return this.authService.login(email);
  }
}
