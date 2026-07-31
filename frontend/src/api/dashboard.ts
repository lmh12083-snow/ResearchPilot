import request from './request'

export interface RecentPaper {
  id: number
  title: string
  project_id: number
  project_name: string
  status: string
  created_at: string
}

export interface RecentProject {
  id: number
  name: string
  paper_count: number
  created_at: string
}

export interface DashboardData {
  project_count: number
  paper_count: number
  recent_papers: RecentPaper[]
  recent_projects: RecentProject[]
}

export const dashboardApi = {
  get() {
    return request.get<DashboardData>('/dashboard')
  },
}
