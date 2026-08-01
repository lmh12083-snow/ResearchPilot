<template>
  <div class="project-detail">
    <!-- Back + Project info -->
    <div class="page-header">
      <el-button text @click="router.push('/projects')">
        ← 返回项目列表
      </el-button>
    </div>

    <el-card v-if="project" class="project-info" shadow="hover">
      <div class="project-info-inner">
        <div>
          <h3>{{ project.name }}</h3>
          <p class="description">{{ project.description || '暂无描述' }}</p>
          <p class="meta">
            <el-icon><Document /></el-icon>
            论文数：{{ project.paper_count }}
            <el-icon style="margin-left:16px"><Clock /></el-icon>
            创建时间：{{ project.created_at }}
          </p>
        </div>
      </div>
    </el-card>

    <!-- Semantic Search -->
    <el-card class="search-card" shadow="never">
      <div class="search-bar">
        <el-input
          v-model="searchQuery"
          placeholder="语义搜索项目内所有论文..."
          size="large"
          clearable
          @clear="clearSearch"
          @keyup.enter="doSearch({ projectId: Number(route.params.id) })"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
          <template #append>
            <el-button :loading="searching" @click="doSearch({ projectId: Number(route.params.id) })">
              搜索
            </el-button>
          </template>
        </el-input>
      </div>
    </el-card>

    <!-- Search Results -->
    <div v-if="hasSearched" class="search-results">
      <div class="section-header">
        <h3>搜索结果（{{ results.length }}）</h3>
        <el-button text size="small" @click="clearSearch">返回论文列表</el-button>
      </div>

      <div v-if="searching" class="center-state">
        <el-skeleton :rows="3" animated />
      </div>

      <el-empty v-else-if="results.length === 0" description="未找到匹配的段落" :image-size="60" />

      <div v-else class="result-list">
        <el-card
          v-for="r in results"
          :key="r.chunk_id"
          class="result-card"
          shadow="hover"
          @click="goToPaper(r.paper_id)"
        >
          <div class="result-header">
            <span class="result-title">{{ r.paper_title }}</span>
            <div class="result-meta">
              <el-tag v-if="r.page_number !== null" size="small" type="warning">p.{{ r.page_number }}</el-tag>
              <el-tag size="small" :type="scoreType(r.score)">{{ (r.score * 100).toFixed(0) }}%</el-tag>
            </div>
          </div>
          <p class="result-excerpt">{{ truncate(r.text, 300) }}</p>
        </el-card>
      </div>
    </div>

    <!-- Papers Section -->
    <div v-else class="papers-section">
      <div class="section-header">
        <h3>论文列表（{{ papers.length }}）</h3>
        <div class="header-actions">
          <el-button :disabled="papers.length < 2" @click="openCompare">
            <el-icon><Switch /></el-icon> 对比论文
          </el-button>
          <el-button :disabled="papers.length < 2" @click="openReview">
            <el-icon><Document /></el-icon> 生成综述
          </el-button>
          <el-upload :show-file-list="false" :before-upload="handleUpload" accept=".pdf">
            <el-button type="primary" :loading="uploading">上传论文</el-button>
          </el-upload>
        </div>
      </div>

      <el-table v-if="papers.length" :data="papers" stripe style="width: 100%">
        <el-table-column prop="file_name" label="原始文件名" min-width="180" />
        <el-table-column prop="title" label="论文标题" min-width="200">
          <template #default="{ row }">
            <span v-if="row.title !== row.file_name">{{ row.title }}</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="作者" min-width="160">
          <template #default="{ row }">
            <span v-if="row.authors">{{ parseAuthors(row.authors) }}</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="doi" label="DOI" min-width="160">
          <template #default="{ row }">
            <span v-if="row.doi" class="text-sm">{{ row.doi }}</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="year" label="年份" width="80" />
        <el-table-column prop="file_size" label="大小" width="90">
          <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="上传时间" width="170" />
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-button type="primary" link @click="goToPaper(row.id)">阅读</el-button>
            <el-button type="danger" link @click="handleDeletePaper(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无论文，请上传 PDF" :image-size="60" />
    </div>

    <!-- Compare Dialog -->
    <el-dialog v-model="compareVisible" title="论文对比（2-5 篇）" width="680px" :close-on-click-modal="false">
      <div v-if="!compareResult" class="compare-form">
        <div class="compare-field">
          <div class="compare-field-label">对比方式</div>
          <el-radio-group v-model="compareMode" size="small">
            <el-radio-button value="single">⚡ 单次生成</el-radio-button>
            <el-radio-button value="agent">🤖 多 Agent 分析</el-radio-button>
          </el-radio-group>
          <div class="compare-mode-hint">{{ compareMode === 'agent' ? '多 Agent 编排：规划维度 → 并行分析各论文 → 聚合对比' : '一次 LLM 调用生成对比，速度最快' }}</div>
        </div>
        <div class="compare-field">
          <div class="compare-field-label">选择论文（最多 {{ COMPARE_MAX }} 篇，按选择顺序对比）</div>
          <el-select
            v-model="comparePaperIds"
            multiple
            :multiple-limit="COMPARE_MAX"
            placeholder="选择 2-5 篇论文"
            style="width: 100%"
          >
            <el-option v-for="p in papers" :key="p.id" :value="p.id" :label="p.title" />
          </el-select>
        </div>

        <div v-if="comparing && streamStatus" class="compare-stream-status">{{ streamStatus }}</div>

        <div class="compare-submit-row">
          <el-button
            type="primary"
            :loading="comparing"
            :disabled="comparePaperIds.length < 2"
            @click="doCompare"
          >
            {{ comparing ? (compareMode === 'agent' ? 'AI 分析中…' : 'AI 正在对比…') : `开始对比（${comparePaperIds.length} 篇）` }}
          </el-button>
          <el-button v-if="comparing && compareMode === 'agent'" text @click="stopCompare">
            停止
          </el-button>
        </div>
      </div>

      <div v-else class="compare-result">
        <div v-if="compareResult.papers?.length" class="compare-overview-list">
          <div v-for="p in compareResult.papers" :key="p.paper_id" class="compare-overview-item">
            <el-tag size="small" type="primary" class="compare-overview-tag">{{ p.title }}</el-tag>
            <span class="compare-overview-text">{{ p.summary || '—' }}</span>
          </div>
        </div>

        <div v-for="section in COMPARE_SECTIONS" :key="section.key" class="compare-section">
          <div class="compare-section-title">{{ section.label }}</div>
          <div class="compare-section-body">{{ compareResult[section.key] || '—' }}</div>
        </div>

        <div class="compare-actions">
          <el-button size="small" @click="resetCompare">重新选择</el-button>
        </div>
      </div>
    </el-dialog>

    <!-- Literature Review Dialog -->
    <el-dialog v-model="reviewVisible" title="文献综述生成" width="820px" :close-on-click-modal="false">
      <div v-if="!reviewMarkdown" class="compare-form">
        <div class="compare-field">
          <div class="compare-field-label">选择论文（至少 2 篇，最多 {{ COMPARE_MAX }} 篇）</div>
          <el-select
            v-model="reviewPaperIds"
            multiple
            :multiple-limit="COMPARE_MAX"
            placeholder="选择要综述的论文"
            style="width: 100%"
          >
            <el-option v-for="p in papers" :key="p.id" :value="p.id" :label="p.title" />
          </el-select>
        </div>

        <div v-if="reviewing && reviewStatus" class="compare-stream-status">{{ reviewStatus }}</div>

        <div class="compare-submit-row">
          <el-button
            type="primary"
            :loading="reviewing"
            :disabled="reviewPaperIds.length < 2"
            @click="doReview"
          >
            {{ reviewing ? 'AI 生成中…' : `生成综述（${reviewPaperIds.length} 篇）` }}
          </el-button>
          <el-button v-if="reviewing" text @click="stopReview">停止</el-button>
        </div>
      </div>

      <div v-else class="review-result">
        <div class="review-actions">
          <el-button size="small" @click="copyReview">复制</el-button>
          <el-button size="small" type="primary" @click="downloadReview">下载 .md</el-button>
          <el-button size="small" @click="resetReview">重新选择</el-button>
        </div>
        <pre class="review-markdown">{{ reviewMarkdown }}</pre>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Document, Clock, Switch } from '@element-plus/icons-vue'
import { projectApi } from '@/api/project'
import { paperApi } from '@/api/paper'
import type { Project } from '@/api/project'
import type { Paper, CompareResult } from '@/api/paper'
import { usePaperSearch } from '@/composables/usePaperSearch'

const COMPARE_MAX = 5

const COMPARE_SECTIONS: { key: keyof CompareResult; label: string }[] = [
  { key: 'similarities', label: '共同点' },
  { key: 'method_differences', label: '方法差异' },
  { key: 'experiment_differences', label: '实验差异' },
  { key: 'conclusion_differences', label: '结论差异' },
  { key: 'strengths_weaknesses', label: '优势与不足' },
  { key: 'final_verdict', label: '对比结论' },
]

const route = useRoute()
const router = useRouter()

const project = ref<Project | null>(null)
const papers = ref<Paper[]>([])
const uploading = ref(false)

const {
  query: searchQuery,
  results,
  searching,
  hasSearched,
  search: doSearch,
  clear: clearSearch,
} = usePaperSearch()

function goToPaper(paperId: number) {
  router.push(`/paper/${paperId}`)
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text
  return text.slice(0, max) + '...'
}

function scoreType(score: number): 'success' | 'warning' | 'info' {
  if (score >= 0.7) return 'success'
  if (score >= 0.4) return 'warning'
  return 'info'
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    UPLOADING: '上传中', PENDING: '待处理', PARSING: '解析中',
    CHUNKING: '分块中', EMBEDDING: '向量化', INDEXING: '建立索引',
    COMPLETED: '已完成', FAILED: '失败',
  }
  return map[status] || status
}

async function fetchProject() {
  try {
    const res = await projectApi.get(Number(route.params.id))
    project.value = res.data
  } catch { /* handled by interceptor */ }
}

async function fetchPapers() {
  try {
    const res = await paperApi.listByProject(Number(route.params.id))
    papers.value = res.data
  } catch { /* handled by interceptor */ }
}

async function handleUpload(file: File): Promise<boolean> {
  uploading.value = true
  try {
    await paperApi.upload(Number(route.params.id), file)
    ElMessage.success('上传成功')
    await fetchPapers()
    await fetchProject()
  } catch { /* handled by interceptor */ }
  finally { uploading.value = false }
  return false
}

async function handleDeletePaper(paperId: number) {
  try {
    await ElMessageBox.confirm('确定要删除该论文吗？文件将一并删除。', '警告', {
      confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning',
    })
    await paperApi.delete(paperId)
    ElMessage.success('删除成功')
    await fetchPapers()
    await fetchProject()
  } catch { /* cancelled */ }
}

const compareVisible = ref(false)
const comparing = ref(false)
const compareMode = ref<'single' | 'agent'>('single')
const comparePaperIds = ref<number[]>([])
const compareResult = ref<CompareResult | null>(null)
const streamStatus = ref('')
const compareController = ref<AbortController | null>(null)

function openCompare() {
  compareVisible.value = true
  compareResult.value = null
  streamStatus.value = ''
}

function resetCompare() {
  compareResult.value = null
  streamStatus.value = ''
}

function stopCompare() {
  compareController.value?.abort()
}

async function doCompare() {
  if (comparePaperIds.value.length < 2) return
  comparing.value = true
  streamStatus.value = ''
  compareResult.value = null
  try {
    if (compareMode.value === 'agent') {
      const controller = new AbortController()
      compareController.value = controller
      await paperApi.comparePapersStream(
        comparePaperIds.value,
        {
          onStatus: (t) => { streamStatus.value = t },
          onResult: (result) => { compareResult.value = result },
          onError: (detail) => ElMessage.error(detail),
        },
        controller.signal,
      )
    } else {
      const res = await paperApi.comparePapers(comparePaperIds.value)
      compareResult.value = res.data
    }
  } catch (e: any) {
    if (e?.name === 'AbortError') {
      ElMessage.info('已停止对比')
    } else {
      ElMessage.error(e?.message || '对比失败')
    }
  } finally {
    comparing.value = false
    compareController.value = null
  }
}

const reviewVisible = ref(false)
const reviewing = ref(false)
const reviewPaperIds = ref<number[]>([])
const reviewMarkdown = ref('')
const reviewStatus = ref('')
const reviewController = ref<AbortController | null>(null)

function openReview() {
  reviewVisible.value = true
  reviewMarkdown.value = ''
  reviewStatus.value = ''
}

function resetReview() {
  reviewMarkdown.value = ''
  reviewStatus.value = ''
}

function stopReview() {
  reviewController.value?.abort()
}

async function doReview() {
  if (reviewPaperIds.value.length < 2) return
  reviewing.value = true
  reviewStatus.value = ''
  reviewMarkdown.value = ''
  try {
    const controller = new AbortController()
    reviewController.value = controller
    await paperApi.reviewStream(
      Number(route.params.id),
      reviewPaperIds.value,
      {
        onStatus: (t) => { reviewStatus.value = t },
        onResult: (md) => { reviewMarkdown.value = md },
        onError: (detail) => ElMessage.error(detail),
      },
      controller.signal,
    )
  } catch (e: any) {
    if (e?.name === 'AbortError') {
      ElMessage.info('已停止生成')
    } else {
      ElMessage.error(e?.message || '生成失败')
    }
  } finally {
    reviewing.value = false
    reviewController.value = null
  }
}

function copyReview() {
  navigator.clipboard.writeText(reviewMarkdown.value)
  ElMessage.success('已复制到剪贴板')
}

function downloadReview() {
  const blob = new Blob([reviewMarkdown.value], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'literature_review.md'
  a.click()
  URL.revokeObjectURL(url)
}

function parseAuthors(authors: string | null): string {
  if (!authors) return '—'
  try {
    const parsed = JSON.parse(authors)
    if (Array.isArray(parsed)) return parsed.slice(0, 3).join('; ') + (parsed.length > 3 ? ' et al.' : '')
    return String(parsed)
  } catch {
    return authors
  }
}

function formatSize(bytes: number | null): string {
  if (bytes === null || bytes === undefined) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function statusType(status: string): 'warning' | 'primary' | 'success' | 'danger' | 'info' {
  switch (status) {
    case 'UPLOADING': case 'PENDING': return 'warning'
    case 'PARSING': case 'CHUNKING': case 'EMBEDDING': case 'INDEXING': return 'primary'
    case 'COMPLETED': return 'success'
    case 'FAILED': return 'danger'
    default: return 'info'
  }
}

onMounted(() => {
  fetchProject()
  fetchPapers()
})
</script>

<style scoped>
.page-header {
  margin-bottom: 16px;
}

.project-info {
  margin-bottom: 20px;
}
.project-info-inner h3 {
  margin: 0 0 8px;
  font-size: 20px;
}
.description {
  color: #64748b;
  margin: 0 0 12px;
  font-size: 14px;
}
.meta {
  color: #94a3b8;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.search-card {
  margin-bottom: 20px;
}

.search-results {
  margin-bottom: 20px;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.section-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.center-state {
  padding: 40px 20px;
}

.result-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}
.result-card {
  cursor: pointer;
}
.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.result-title {
  font-weight: 600;
  font-size: 14px;
  color: #3b82f6;
}
.result-meta {
  display: flex;
  gap: 8px;
  align-items: center;
}
.result-excerpt {
  margin: 0;
  font-size: 13px;
  color: #64748b;
  line-height: 1.6;
}

.papers-section {
  margin-top: 8px;
}
.text-muted { color: #94a3b8; font-size: 13px; }
.text-sm { font-size: 13px; }

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.compare-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.compare-field-label {
  font-size: 13px;
  color: #64748b;
  margin-bottom: 6px;
}
.compare-mode-hint {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 6px;
}
.compare-stream-status {
  font-size: 13px;
  color: #3b82f6;
  background: #eff6ff;
  border-radius: 6px;
  padding: 8px 12px;
  line-height: 1.5;
}
.compare-submit-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.compare-result {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-height: 60vh;
  overflow-y: auto;
  padding-right: 4px;
}
.compare-overview-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.compare-overview-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.compare-overview-tag {
  flex-shrink: 0;
  max-width: 45%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.compare-overview-text {
  font-size: 13px;
  color: #334155;
  line-height: 1.6;
}
.compare-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #3b82f6;
  margin-bottom: 4px;
}
.compare-section-body {
  font-size: 13px;
  color: #334155;
  line-height: 1.7;
  white-space: pre-wrap;
}
.compare-actions {
  display: flex;
  justify-content: flex-end;
}

.review-result {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.review-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.review-markdown {
  margin: 0;
  max-height: 60vh;
  overflow-y: auto;
  background: #f8fafc;
  border-radius: 8px;
  padding: 16px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 12.5px;
  line-height: 1.7;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
