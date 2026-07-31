<template>
  <div class="upload-page">
    <!-- Step 1: Project Selection -->
    <el-card class="section-card" shadow="hover">
      <template #header>
        <span class="step-label">1. 选择研究项目</span>
      </template>
      <div class="project-selector">
        <el-select
          v-model="selectedProjectId"
          placeholder="请选择项目"
          size="large"
          style="width: 360px"
          @change="onProjectChange"
        >
          <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id">
            <span>{{ p.name }}</span>
            <span class="option-meta">{{ p.paper_count }} 篇</span>
          </el-option>
        </el-select>
        <el-button size="large" @click="showCreateDialog = true">+ 新建项目</el-button>
      </div>
    </el-card>

    <!-- Step 2: Upload -->
    <el-card class="section-card" :class="{ 'is-disabled': !selectedProjectId }" shadow="hover">
      <template #header>
        <span class="step-label">2. 上传论文</span>
      </template>

      <el-row :gutter="24">
        <el-col :span="14">
          <div
            class="drop-zone"
            :class="{ 'is-active': dragOver, 'is-disabled': !selectedProjectId }"
            @dragover.prevent="dragOver = true"
            @dragleave.prevent="dragOver = false"
            @drop.prevent="onDrop"
            @click="triggerUpload"
          >
            <el-icon class="upload-icon" :size="40"><UploadFilled /></el-icon>
            <p class="upload-text">
              {{ selectedProjectId ? '拖拽 PDF 到此处，或点击选择文件' : '请先选择项目' }}
            </p>
            <p class="upload-hint">仅支持 PDF 格式</p>
            <input ref="fileInputRef" type="file" accept=".pdf" style="display: none" @change="onFileSelected" />
          </div>
        </el-col>
        <el-col :span="10">
          <div class="arxiv-section">
            <h4>从 arXiv 导入</h4>
            <p class="arxiv-hint">输入 arXiv ID 或完整 URL 即可自动下载</p>
            <el-input
              v-model="arxivInput"
              placeholder="例如 1706.03762"
              size="large"
              :disabled="!selectedProjectId"
              clearable
            >
              <template #append>
                <el-button :loading="arxivLoading" :disabled="!arxivInput || !selectedProjectId" @click="handleArxivImport">
                  导入
                </el-button>
              </template>
            </el-input>
            <div class="arxiv-examples">
              常见 ID：
              <a href="javascript:void(0)" @click="arxivInput = '1706.03762'">1706.03762</a>
              <a href="javascript:void(0)" @click="arxivInput = '2005.11401'">2005.11401</a>
              <a href="javascript:void(0)" @click="arxivInput = '2303.08774'">2303.08774</a>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- Upload Queue -->
    <el-card v-if="queue.length" class="section-card" shadow="hover">
      <template #header>
        <span class="step-label">处理进度</span>
      </template>
      <div v-for="item in queue" :key="item.paper.id" class="queue-item">
        <div class="queue-info">
          <div class="queue-title">{{ item.paper.title }}</div>
          <div class="queue-meta">
            <span class="source-tag" :class="item.paper.source_type">
              {{ item.paper.source_type === 'arxiv' ? 'arXiv' : '上传' }}
            </span>
            <span class="file-size">{{ formatSize(item.paper.file_size) }}</span>
          </div>
        </div>
        <div class="queue-status">
          <el-tag :type="statusType(item.paper.status)" size="small">
            {{ statusLabel(item.paper.status) }}
          </el-tag>
          <el-progress
            v-if="item.paper.processing_progress > 0 && item.paper.processing_progress < 100"
            :percentage="item.paper.processing_progress"
            :stroke-width="4"
            style="width: 120px"
          />
          <el-button
            v-if="item.paper.status === 'FAILED'"
            text type="danger" size="small"
            @click="handleDelete(item.paper.id)"
          >删除</el-button>
        </div>
      </div>
    </el-card>

    <!-- Recent Papers -->
    <el-card v-if="selectedProjectId && recentPapers.length" class="section-card" shadow="hover">
      <template #header>
        <div class="section-card-header">
          <span>项目论文列表</span>
          <el-button text type="primary" size="small" @click="router.push(`/project/${selectedProjectId}`)">
            查看全部 →
          </el-button>
        </div>
      </template>
      <el-table :data="recentPapers.slice(0, 5)" stripe style="width: 100%">
        <el-table-column prop="title" label="文件名" min-width="240" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="80">
          <template #default="{ row }">
            <span class="source-tag" :class="row.source_type">{{ row.source_type }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="上传时间" width="170" />
      </el-table>
    </el-card>

    <!-- Create Project Dialog -->
    <el-dialog v-model="showCreateDialog" title="新建项目" width="480px">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="60px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="createForm.name" placeholder="项目名称" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="createForm.description" type="textarea" :rows="3" placeholder="项目描述（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreateProject">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { projectApi } from '@/api/project'
import { paperApi } from '@/api/paper'
import type { Project } from '@/api/project'
import type { Paper, PaperStatus } from '@/api/paper'

const router = useRouter()

const projects = ref<Project[]>([])
const selectedProjectId = ref<number | null>(null)
const fileInputRef = ref<HTMLInputElement>()
const dragOver = ref(false)
const arxivInput = ref('')
const arxivLoading = ref(false)
const queue = ref<{ paper: Paper; timer: ReturnType<typeof setInterval> | null }[]>([])
const recentPapers = ref<Paper[]>([])
const showCreateDialog = ref(false)
const creating = ref(false)
const createFormRef = ref<FormInstance>()
const createForm = ref({ name: '', description: '' })
const createRules: FormRules = {
  name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
}
const POLL_INTERVAL = 2000

onMounted(() => { fetchProjects() })
onUnmounted(() => {
  queue.value.forEach((item) => item.timer && clearInterval(item.timer))
})

async function fetchProjects() {
  try { const res = await projectApi.list(); projects.value = res.data } catch { /* */ }
}

function onProjectChange() {
  if (selectedProjectId.value) fetchRecentPapers()
  else recentPapers.value = []
}

async function fetchRecentPapers() {
  if (!selectedProjectId.value) return
  try { const res = await paperApi.listByProject(selectedProjectId.value); recentPapers.value = res.data } catch { /* */ }
}

function triggerUpload() {
  if (!selectedProjectId.value) return
  fileInputRef.value?.click()
}

function onDrop(e: DragEvent) {
  dragOver.value = false
  if (!selectedProjectId.value) { ElMessage.warning('请先选择项目'); return }
  const file = e.dataTransfer?.files?.[0]
  if (file) uploadFile(file)
}

function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) uploadFile(file)
  if (fileInputRef.value) fileInputRef.value.value = ''
}

async function uploadFile(file: File) {
  if (!selectedProjectId.value) return
  if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
    ElMessage.error('仅支持 PDF 格式'); return
  }
  try {
    const res = await paperApi.upload(selectedProjectId.value, file)
    addToQueue(res.data)
    ElMessage.success(`${file.name} 上传成功`)
    await fetchRecentPapers()
  } catch { /* */ }
}

async function handleArxivImport() {
  if (!selectedProjectId.value || !arxivInput.value) return
  const arxivId = extractArxivId(arxivInput.value)
  if (!arxivId) { ElMessage.error('无效的 arXiv ID 或 URL'); return }
  arxivLoading.value = true
  try {
    const res = await paperApi.importArxiv({ project_id: selectedProjectId.value, arxiv_id: arxivId })
    addToQueue(res.data)
    arxivInput.value = ''
    ElMessage.success('arXiv 论文导入成功')
    await fetchRecentPapers()
  } catch { /* */ }
  finally { arxivLoading.value = false }
}

function extractArxivId(input: string): string | null {
  const t = input.trim()
  if (/^\d{4}\.\d{4,5}(v\d+)?$/.test(t)) return t
  const m = t.match(/arxiv\.org\/(?:abs|pdf)\/(\d{4}\.\d{4,5}(v\d+)?)/)
  return m ? m[1] : null
}

function addToQueue(paper: Paper) {
  if (queue.value.some((item) => item.paper.id === paper.id)) return
  const timer = setInterval(() => pollStatus(paper.id), POLL_INTERVAL)
  queue.value.push({ paper, timer })
  pollStatus(paper.id)
}

async function pollStatus(paperId: number) {
  try {
    const res = await paperApi.getStatus(paperId)
    const updated = res.data
    const item = queue.value.find((q) => q.paper.id === paperId)
    if (item) {
      item.paper = { ...item.paper, ...updated }
      if (['COMPLETED', 'FAILED'].includes(updated.status)) {
        if (item.timer) clearInterval(item.timer)
        item.timer = null
      }
    }
    const idx = recentPapers.value.findIndex((p) => p.id === paperId)
    if (idx !== -1) recentPapers.value[idx] = { ...recentPapers.value[idx], ...updated }
  } catch { /* */ }
}

async function handleDelete(paperId: number) {
  try {
    await ElMessageBox.confirm('确定删除该论文？', '警告', {
      confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning',
    })
    await paperApi.delete(paperId)
    const item = queue.value.find((q) => q.paper.id === paperId)
    if (item?.timer) clearInterval(item.timer)
    queue.value = queue.value.filter((q) => q.paper.id !== paperId)
    await fetchRecentPapers()
    ElMessage.success('已删除')
  } catch { /* */ }
}

async function handleCreateProject() {
  const valid = await createFormRef.value?.validate().catch(() => false)
  if (!valid) return
  creating.value = true
  try {
    const res = await projectApi.create(createForm.value)
    projects.value.push(res.data)
    selectedProjectId.value = res.data.id
    showCreateDialog.value = false
    createForm.value = { name: '', description: '' }
    ElMessage.success('项目创建成功')
  } catch { /* */ }
  finally { creating.value = false }
}

function formatSize(bytes: number | null): string {
  if (!bytes) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function statusLabel(status: PaperStatus): string {
  const map: Record<PaperStatus, string> = {
    UPLOADING: '上传中', PENDING: '待处理', PARSING: '解析中',
    CHUNKING: '分块中', EMBEDDING: '向量化', INDEXING: '建立索引',
    COMPLETED: '已完成', FAILED: '失败',
  }
  return map[status] || status
}

function statusType(status: PaperStatus): 'warning' | 'primary' | 'success' | 'danger' | 'info' {
  switch (status) {
    case 'UPLOADING': case 'PENDING': return 'warning'
    case 'PARSING': case 'CHUNKING': case 'EMBEDDING': case 'INDEXING': return 'primary'
    case 'COMPLETED': return 'success'
    case 'FAILED': return 'danger'
    default: return 'info'
  }
}
</script>

<style scoped>
.section-card {
  margin-bottom: 20px;
}
.section-card.is-disabled { opacity: 0.6; }
.step-label { font-weight: 600; color: #1e293b; }
.section-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.project-selector {
  display: flex;
  align-items: center;
  gap: 12px;
}
.option-meta {
  float: right;
  color: #94a3b8;
  font-size: 12px;
  margin-left: 16px;
}

.drop-zone {
  border: 2px dashed #d9d9d9;
  border-radius: 12px;
  padding: 32px 24px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s;
  background: #fafafa;
}
.drop-zone:hover,
.drop-zone.is-active {
  border-color: #3b82f6;
  background: #eff6ff;
}
.drop-zone.is-disabled { cursor: not-allowed; }
.upload-icon { color: #c0c4cc; margin-bottom: 12px; }
.drop-zone.is-active .upload-icon,
.drop-zone:hover .upload-icon { color: #3b82f6; }
.upload-text { color: #64748b; font-size: 14px; margin: 0 0 4px; }
.upload-hint { color: #c0c4cc; font-size: 12px; margin: 0; }

.arxiv-section h4 { margin: 0 0 8px; font-size: 15px; color: #1e293b; }
.arxiv-hint { color: #94a3b8; font-size: 13px; margin: 0 0 12px; }
.arxiv-examples { margin-top: 8px; font-size: 12px; color: #94a3b8; display: flex; gap: 8px; }
.arxiv-examples a { color: #3b82f6; text-decoration: none; }

.queue-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid #f1f5f9;
}
.queue-item:last-child { border-bottom: none; }
.queue-title { font-size: 14px; font-weight: 500; margin-bottom: 4px; }
.queue-meta { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #94a3b8; }
.queue-status { display: flex; align-items: center; gap: 12px; }

.source-tag {
  display: inline-block;
  padding: 0 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}
.source-tag.arxiv { background: #eff6ff; color: #3b82f6; }
.source-tag.upload { background: #faf5ff; color: #8b5cf6; }
</style>
