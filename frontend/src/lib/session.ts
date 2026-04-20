export interface UserData {
  user_id: string;
  username: string;
  name: string | null;
  experience: string | null;
  target_company: string | null;
  target_level: string | null;
  preferences: string | null;
  is_onboarded: boolean;
  created_at: string;
  updated_at: string | null;
}

export interface AuthSession {
  user: UserData;
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
}
