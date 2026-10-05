export interface HasEmail {
  email: string;
}

export class BaseEntity {
  id = '';
}

export class UserEntity extends BaseEntity implements HasEmail {
  email = '';
}
