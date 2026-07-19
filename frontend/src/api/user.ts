import request from './request'

export interface LoginRequest {
  username: string
  password: string
}

export interface RegisterRequest {
  username: string
  email: string
  password: string
}

export interface UserInfo {
  id: number
  username: string
  email: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: UserInfo
}

export const userApi = {
  login(data: LoginRequest) {
    return request.post<LoginResponse>('/auth/login', data)
  },

  register(data: RegisterRequest) {
    return request.post<UserInfo>('/auth/register', data)
  },

  getProfile() {
    return request.get<UserInfo>('/auth/me')
  },
}
