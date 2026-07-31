import request from './request'

export interface FeatureStat {
  feature: string
  calls: number
  total_tokens: number
}

export interface LLMStats {
  today_calls: number
  today_tokens: number
  total_calls: number
  total_tokens: number
  prompt_tokens: number
  completion_tokens: number
  by_feature: FeatureStat[]
}

export const llmApi = {
  /** Aggregate LLM token usage statistics. */
  stats() {
    return request.get<LLMStats>('/llm/stats')
  },
}
