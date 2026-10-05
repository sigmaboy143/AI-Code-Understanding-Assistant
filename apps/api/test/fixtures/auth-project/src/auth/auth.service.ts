import { UserRepository } from '../users/user.repository.js';
import { JwtService } from './jwt.service.js';

export class AuthService {
  constructor(
    private readonly userRepository: UserRepository,
    private readonly jwtService: JwtService,
  ) {}

  async login(email: string): Promise<string> {
    const user = await this.userRepository.findByEmail(email);
    return this.jwtService.sign({ sub: user.id });
  }
}
