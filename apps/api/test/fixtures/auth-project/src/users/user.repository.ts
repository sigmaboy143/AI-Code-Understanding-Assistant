import { UserEntity } from './user.entity.js';

export class UserRepository {
  findByEmail(email: string): Promise<UserEntity> {
    const user = new UserEntity();
    user.email = email;
    return Promise.resolve(user);
  }
}
