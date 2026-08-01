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
  avatar: string | null
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: UserInfo
}

export interface UpdateProfileRequest {
  username?: string
  email?: string
}

export interface ChangePasswordRequest {
  old_password: string
  new_password: string
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

  logout() {
    return request.post('/auth/logout')
  },

  updateProfile(data: UpdateProfileRequest) {
    return request.patch<UserInfo>('/auth/me', data)
  },

  uploadAvatar(file: File) {
    const form = new FormData()
    form.append('file', file)
    return request.post<UserInfo>('/auth/avatar', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  deleteAvatar() {
    return request.delete<UserInfo>('/auth/avatar')
  },

  /** Auth-required avatar URL for <img> — embeds the JWT as a query param. */
  getAvatarUrl(): string {
    const token = localStorage.getItem('token') || ''
    return `/api/v1/auth/avatar?token=${encodeURIComponent(token)}&v=${Date.now()}`
  },

  changePassword(data: ChangePasswordRequest) {
    return request.put('/auth/password', data)
  },
}
