import request from './request'

export interface EvalMetrics {
  hit_at_1: number
  hit_at_3: number
  hit_at_5: number
  mrr: number
  answer_accuracy: number
  faithfulness: number
}

export interface EvalRun {
  id: number
  project_id: number
  status: 'running' | 'completed' | 'failed'
  progress: number
  question_count: number
  sample_size: number
  metrics: EvalMetrics | null
  error_message: string | null
  duration_seconds: number | null
  created_at: string
}

export interface EvalQuestion {
  id: number
  paper_id: number
  paper_title: string
  question: string
  gold_chunk_id: string
  gold_text: string
  retrieved_rank: number | null
  hit: boolean | null
  answer: string | null
  answer_correct: boolean | null
  faithful: boolean | null
  judge_reasoning: string | null
}

export const evalApi = {
  createRun(data: { project_id: number; sample_size?: number }) {
    return request.post<EvalRun>('/eval/runs', data)
  },

  listRuns() {
    return request.get<EvalRun[]>('/eval/runs')
  },

  getRun(id: number) {
    return request.get<EvalRun>(`/eval/runs/${id}`)
  },

  getQuestions(runId: number) {
    return request.get<EvalQuestion[]>(`/eval/runs/${runId}/questions`)
  },

  deleteRun(id: number) {
    return request.delete(`/eval/runs/${id}`)
  },
}
