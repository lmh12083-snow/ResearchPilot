import request from './request'

export interface Project {
  id: number
  name: string
  description: string
  created_at: string
  updated_at: string
}

export interface CreateProjectRequest {
  name: string
  description?: string
}

export const projectApi = {
  list() {
    return request.get<Project[]>('/projects')
  },

  get(id: number) {
    return request.get<Project>(`/projects/${id}`)
  },

  create(data: CreateProjectRequest) {
    return request.post<Project>('/projects', data)
  },

  update(id: number, data: Partial<CreateProjectRequest>) {
    return request.put<Project>(`/projects/${id}`, data)
  },

  delete(id: number) {
    return request.delete(`/projects/${id}`)
  },
}
