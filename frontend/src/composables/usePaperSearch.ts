import { ref } from 'vue'
import { paperApi } from '@/api/paper'
import type { SearchResult } from '@/api/paper'

export function usePaperSearch() {
  const query = ref('')
  const results = ref<SearchResult[]>([])
  const searching = ref(false)
  const hasSearched = ref(false)

  async function search(opts: { projectId?: number; paperId?: number }) {
    const q = query.value.trim()
    if (!q) {
      results.value = []
      hasSearched.value = false
      return
    }

    searching.value = true
    hasSearched.value = true
    try {
      const payload: {
        query: string
        top_k: number
        project_id?: number
        paper_id?: number
      } = {
        query: q,
        top_k: 10,
      }
      if (opts.projectId) payload.project_id = opts.projectId
      if (opts.paperId) payload.paper_id = opts.paperId

      const res = await paperApi.search(payload)
      results.value = res.data.results
    } catch {
      results.value = []
    } finally {
      searching.value = false
    }
  }

  function clear() {
    query.value = ''
    results.value = []
    hasSearched.value = false
    searching.value = false
  }

  return { query, results, searching, hasSearched, search, clear }
}
