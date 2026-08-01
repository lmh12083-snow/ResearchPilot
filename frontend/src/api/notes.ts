import request from './request'

export interface Note {
  id: number
  paper_id: number
  project_id: number
  anchor_text: string | null
  content: string | null
  tags: string[]
  ai_summary: string | null
  created_at: string
  updated_at: string
}

export interface NoteCreateRequest {
  paper_id: number
  anchor_text?: string
  content?: string
  tags?: string[]
  summarize?: boolean
}

export interface NoteUpdateRequest {
  anchor_text?: string
  content?: string
  tags?: string[]
}

export const noteApi = {
  create(data: NoteCreateRequest) {
    return request.post<Note>('/notes', data)
  },

  list(params: { paper_id?: number; project_id?: number } = {}) {
    return request.get<Note[]>('/notes', { params })
  },

  update(id: number, data: NoteUpdateRequest) {
    return request.put<Note>(`/notes/${id}`, data)
  },

  remove(id: number) {
    return request.delete(`/notes/${id}`)
  },

  summarize(id: number) {
    return request.post<Note>(`/notes/${id}/summarize`)
  },

  /** Download notes as Markdown via axios (auth header attached automatically). */
  async exportMarkdown(projectId: number, paperId?: number) {
    const res = await request.get('/notes/export', {
      params: { project_id: projectId, paper_id: paperId },
      responseType: 'blob',
    })
    const url = URL.createObjectURL(res.data as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'notes.md'
    a.click()
    URL.revokeObjectURL(url)
  },
}
