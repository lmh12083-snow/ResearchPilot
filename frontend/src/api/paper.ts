import request from './request'

export type PaperStatus =
  | 'UPLOADING'
  | 'PENDING'
  | 'PARSING'
  | 'CHUNKING'
  | 'EMBEDDING'
  | 'INDEXING'
  | 'COMPLETED'
  | 'FAILED'

export type PaperSource = 'upload' | 'arxiv'

export interface Paper {
  id: number
  project_id: number
  title: string
  file_name: string | null
  file_path: string | null
  file_size: number | null
  page_count: number | null
  source_type: PaperSource
  arxiv_id: string | null
  status: PaperStatus
  processing_progress: number
  error_message: string | null
  created_at: string
  updated_at: string
  // Metadata
  authors: string | null
  keywords: string | null
  abstract: string | null
  doi: string | null
  year: number | null
}

export interface PaperStatusResponse {
  id: number
  project_id: number
  title: string
  status: PaperStatus
  processing_progress: number
  source_type: PaperSource
  arxiv_id: string | null
  page_count: number | null
  file_size: number | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface ArxivImportRequest {
  project_id: number
  arxiv_id: string
}

// ── Search ─────────────────────────────────────────────────────

export interface SearchRequest {
  query: string
  project_id?: number
  paper_id?: number
  top_k?: number
}

export interface SearchResult {
  chunk_id: string
  text: string
  paper_id: number
  paper_title: string
  page_number: number | null
  chunk_index: number
  score: number
}

export interface SearchResponse {
  results: SearchResult[]
}

// ── Analysis ─────────────────────────────────────────────────────

export interface Analysis {
  abstract: string | null
  innovation: string | null
  methods: string | null
  experiments: string | null
  limitations: string | null
  related_work: string | null
  one_sentence: string | null
  pros_cons: string | null
}

// ── Chat ─────────────────────────────────────────────────────────

export interface ChatMessage {
  id: number
  paper_id: number
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface Citation {
  page_number: number | null
  chunk_index: number | null
  text: string | null
}

export type ChatMode = 'paper_only' | 'project_search' | 'web_search' | 'auto'

export interface ChatRequest {
  message: string
  mode?: ChatMode
}

export interface ChatResponse {
  reply: string
  citations: Citation[]
  has_answer: boolean
  suggestions: string[]
}

export interface ChatStreamMeta {
  citations: Citation[]
  has_answer: boolean
  suggestions: string[]
}

export interface ChatStreamHandlers {
  onMeta: (meta: ChatStreamMeta) => void
  onDelta: (text: string) => void
  onDone: (data: { message_id: number | null; reply: string }) => void
  onStatus?: (text: string) => void
  onError?: (detail: string) => void
}

// ── Paper Comparison ───────────────────────────────────────────

export interface CompareResult {
  overview: string | null
  similarities: string | null
  method_differences: string | null
  experiment_differences: string | null
  conclusion_differences: string | null
  strengths_weaknesses: string | null
  final_verdict: string | null
}

// ── Paper Content ──────────────────────────────────────────────

export interface PaperContent {
  id: number
  project_id: number
  title: string
  text: string
  page_count: number | null
  chunk_count: number | null
  status: PaperStatus
}

export const paperApi = {
  /** Upload a PDF file to a project. */
  upload(projectId: number, file: File) {
    const form = new FormData()
    form.append('project_id', String(projectId))
    form.append('file', file)
    return request.post<Paper>('/papers/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  /** Import a paper from arXiv by ID. */
  importArxiv(data: ArxivImportRequest) {
    return request.post<Paper>('/papers/arxiv', data)
  },

  /** Get processing status for a paper. */
  getStatus(paperId: number) {
    return request.get<PaperStatusResponse>(`/papers/${paperId}/status`)
  },

  /** List papers in a project. */
  listByProject(projectId: number) {
    return request.get<Paper[]>(`/projects/${projectId}/papers`)
  },

  /** Get a single paper by id. */
  get(paperId: number) {
    return request.get<Paper>(`/papers/${paperId}`)
  },

  /** Delete a paper (and its file). */
  delete(paperId: number) {
    return request.delete(`/papers/${paperId}`)
  },

  /** Semantic search across paper chunks. */
  search(data: SearchRequest) {
    return request.post<SearchResponse>('/papers/search', data)
  },

  /** Get full parsed text content for reading. */
  getContent(paperId: number) {
    return request.get<PaperContent>(`/papers/${paperId}/content`)
  },

  /** Get the PDF file URL for in-browser viewing. */
  getFileUrl(paperId: number): string {
    return `/api/v1/papers/${paperId}/file`
  },

  /** Get or generate paper analysis. */
  getAnalysis(paperId: number) {
    return request.get<Analysis>(`/papers/${paperId}/analysis`)
  },

  /** Regenerate paper analysis. */
  regenerateAnalysis(paperId: number) {
    return request.post<Analysis>(`/papers/${paperId}/analysis`)
  },

  /** Send a chat message about the paper. */
  sendChat(paperId: number, data: ChatRequest) {
    return request.post<ChatResponse>(`/papers/${paperId}/chat`, data)
  },

  /**
   * Stream a chat message via SSE (fetch-based; axios can't stream).
   * Events: meta → delta* → done / error.
   */
  async sendChatStream(
    paperId: number,
    data: ChatRequest,
    handlers: ChatStreamHandlers,
    signal?: AbortSignal,
  ): Promise<void> {
    const token = localStorage.getItem('token') || ''
    const resp = await fetch(`/api/v1/papers/${paperId}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(data),
      signal,
    })

    if (!resp.ok) {
      let detail = '发送失败'
      try {
        const err = await resp.json()
        detail = err?.detail || detail
      } catch { /* ignore */ }
      throw new Error(detail)
    }
    if (!resp.body) throw new Error('响应流不可用')

    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    const onError = handlers.onError || (() => {})

    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // Parse complete SSE frames (separated by blank lines)
      let idx: number
      while ((idx = buffer.indexOf('\n\n')) >= 0) {
        const raw = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)

        let event = 'message'
        let dataStr = ''
        for (const line of raw.split('\n')) {
          if (line.startsWith('event:')) event = line.slice(6).trim()
          else if (line.startsWith('data:')) dataStr += line.slice(5).trim()
        }
        if (!dataStr) continue

        let payload: any
        try { payload = JSON.parse(dataStr) } catch { continue }

        if (event === 'meta') handlers.onMeta(payload)
        else if (event === 'delta') handlers.onDelta(payload.text)
        else if (event === 'done') handlers.onDone(payload)
        else if (event === 'status') handlers.onStatus?.(payload.text)
        else if (event === 'error') onError(payload.detail)
      }
    }
  },

  /** Get chat history for a paper. */
  getChatHistory(paperId: number) {
    return request.get<ChatMessage[]>(`/papers/${paperId}/chat`)
  },

  /** Generate a structured comparison of two papers. */
  comparePapers(paperIds: number[]) {
    return request.post<CompareResult>('/papers/compare', { paper_ids: paperIds })
  },
}
