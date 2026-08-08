<template>
  <div class="eval-page">
    <!-- 配置 + 说明 -->
    <el-card shadow="hover" class="config-card">
      <div class="config-row">
        <el-select
          v-model="projectId"
          placeholder="选择项目"
          style="width: 240px"
          :loading="loadingProjects"
          @change="resetView"
        >
          <el-option v-for="p in projects" :key="p.id" :value="p.id" :label="p.name" />
        </el-select>

        <div class="sample-field">
          <span class="sample-label">每篇抽样题数</span>
          <el-input-number v-model="sampleSize" :min="2" :max="20" :step="1" />
        </div>

        <el-button
          type="primary"
          :loading="starting"
          :disabled="!projectId || anyRunning"
          @click="startEval"
        >
          {{ anyRunning ? '评测进行中…' : '开始评测' }}
        </el-button>
      </div>

      <p class="config-hint">
        用论文原文自动生成 Q&amp;A 测试集，分离评测<strong>检索质量</strong>（hit@1/3/5、MRR）
        与<strong>回答质量</strong>（LLM 裁判判定的正确率、忠实度）。运行含多次 LLM 调用，
        按 <code>eval</code> 计入用量统计。
      </p>
    </el-card>

    <!-- 进行中 -->
    <el-card v-if="currentRun && currentRun.status === 'running'" shadow="hover" class="run-card">
      <div class="run-title">正在评测…</div>
      <el-progress
        :percentage="progressPct"
        :stroke-width="14"
        :text-inside="true"
      />
      <div class="run-status-text">
        已处理 {{ currentRun.progress }} / {{ currentRun.question_count }} 题
      </div>
    </el-card>

    <!-- 失败 -->
    <el-alert
      v-else-if="currentRun && currentRun.status === 'failed'"
      type="error"
      :title="currentRun.error_message || '评测失败'"
      :closable="false"
      show-icon
      class="run-card"
    />

    <!-- 指标 -->
    <el-card v-if="currentRun && currentRun.metrics" shadow="hover" class="run-card">
      <div class="run-header">
        <div class="run-title">评测结果</div>
        <span class="run-meta">
          {{ currentRun.question_count }} 题 · 耗时 {{ currentRun.duration_seconds ?? 0 }}s
        </span>
      </div>

      <div class="metric-grid">
        <div class="metric-box">
          <div class="metric-num">{{ pct(currentRun.metrics.hit_at_1) }}</div>
          <div class="metric-label">Hit@1</div>
          <div class="metric-desc">金标准片段排在首位</div>
        </div>
        <div class="metric-box">
          <div class="metric-num">{{ pct(currentRun.metrics.hit_at_3) }}</div>
          <div class="metric-label">Hit@3</div>
          <div class="metric-desc">金标准片段进入前三</div>
        </div>
        <div class="metric-box">
          <div class="metric-num">{{ pct(currentRun.metrics.hit_at_5) }}</div>
          <div class="metric-label">Hit@5</div>
          <div class="metric-desc">金标准片段进入前五</div>
        </div>
        <div class="metric-box">
          <div class="metric-num">{{ currentRun.metrics.mrr.toFixed(3) }}</div>
          <div class="metric-label">MRR</div>
          <div class="metric-desc">平均倒数排名</div>
        </div>
        <div class="metric-box">
          <div class="metric-num">{{ pct(currentRun.metrics.answer_accuracy) }}</div>
          <div class="metric-label">回答正确率</div>
          <div class="metric-desc">LLM 裁判判定</div>
        </div>
        <div class="metric-box">
          <div class="metric-num">{{ pct(currentRun.metrics.faithfulness) }}</div>
          <div class="metric-label">忠实度</div>
          <div class="metric-desc">无编造/无矛盾</div>
        </div>
      </div>
    </el-card>

    <!-- 明细表 -->
    <el-card v-if="currentRun && questions.length" shadow="hover" class="run-card">
      <div class="run-title">题目明细</div>
      <el-table :data="questions" stripe>
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="q-detail">
              <div class="q-detail-block">
                <div class="q-detail-label">标准答案片段（gold chunk #{{ row.gold_chunk_id }}）</div>
                <div class="q-detail-body">{{ row.gold_text }}</div>
              </div>
              <div class="q-detail-block">
                <div class="q-detail-label">参考答案</div>
                <div class="q-detail-body">{{ row.answer || '—' }}</div>
              </div>
              <div class="q-detail-block">
                <div class="q-detail-label">裁判理由</div>
                <div class="q-detail-body">{{ row.judge_reasoning || '—' }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="question" label="问题" min-width="260" />
        <el-table-column prop="paper_title" label="来源论文" min-width="150" />
        <el-table-column label="检索" width="120">
          <template #default="{ row }">
            <el-tag v-if="row.hit" size="small" type="success">命中 #{{ row.retrieved_rank }}</el-tag>
            <el-tag v-else size="small" type="danger">未命中</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="回答" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.answer_correct !== null" size="small" :type="row.answer_correct ? 'success' : 'danger'">
              {{ row.answer_correct ? '正确' : '错误' }}
            </el-tag>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="忠实" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.faithful !== null" size="small" :type="row.faithful ? 'success' : 'danger'">
              {{ row.faithful ? '忠实' : '幻觉' }}
            </el-tag>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 历史 -->
    <el-card v-if="runs.length" shadow="hover" class="run-card">
      <div class="run-title">历史评测</div>
      <div v-for="r in runs" :key="r.id" class="history-row" @click="viewRun(r.id)">
        <el-icon class="history-icon"><Document /></el-icon>
        <span class="history-proj">{{ projectName(r.project_id) }}</span>
        <el-tag size="small" :type="statusType(r.status)" class="history-status">{{ statusLabel(r.status) }}</el-tag>
        <span class="history-meta">{{ r.question_count }} 题 · {{ r.created_at }}</span>
        <el-button
          size="small"
          text
          type="danger"
          class="history-del"
          @click.stop="removeRun(r.id)"
        >删除</el-button>
      </div>
    </el-card>

    <el-empty v-else-if="!loadingRuns" description="还没有评测记录，选择项目开始第一次评测吧" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Document } from '@element-plus/icons-vue'
import { projectApi, type Project } from '@/api/project'
import { evalApi, type EvalRun, type EvalQuestion } from '@/api/eval'

const projects = ref<Project[]>([])
const loadingProjects = ref(false)
const projectId = ref<number | null>(null)
const sampleSize = ref(5)
const starting = ref(false)

const runs = ref<EvalRun[]>([])
const loadingRuns = ref(false)
const currentRun = ref<EvalRun | null>(null)
const questions = ref<EvalQuestion[]>([])
let pollTimer: ReturnType<typeof setInterval> | null = null

const anyRunning = computed(() => runs.value.some((r) => r.status === 'running'))
const progressPct = computed(() => {
  const run = currentRun.value
  if (!run || !run.question_count) return 0
  return Math.round((run.progress / run.question_count) * 100)
})

function pct(v: number): string {
  return `${(v * 100).toFixed(0)}%`
}

function projectName(id: number): string {
  return projects.value.find((p) => p.id === id)?.name || `项目#${id}`
}

function statusType(s: string): 'primary' | 'success' | 'danger' | 'info' {
  return s === 'running' ? 'primary' : s === 'completed' ? 'success' : 'danger'
}
function statusLabel(s: string): string {
  return s === 'running' ? '进行中' : s === 'completed' ? '已完成' : '失败'
}

async function loadProjects() {
  loadingProjects.value = true
  try {
    const res = await projectApi.list()
    projects.value = res.data
    if (!projectId.value && res.data.length) projectId.value = res.data[0].id
  } finally {
    loadingProjects.value = false
  }
}

async function loadRuns() {
  loadingRuns.value = true
  try {
    const res = await evalApi.listRuns()
    runs.value = res.data
    if (res.data.length) await viewRun(res.data[0].id)
  } finally {
    loadingRuns.value = false
  }
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function viewRun(id: number) {
  stopPolling()
  const found = runs.value.find((r) => r.id === id)
  currentRun.value = found ? { ...found } : null
  if (currentRun.value?.status === 'running') startPolling(id)
  const [runRes, qRes] = await Promise.all([
    evalApi.getRun(id),
    evalApi.getQuestions(id),
  ])
  currentRun.value = runRes.data
  questions.value = qRes.data
}

function startPolling(id: number) {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const res = await evalApi.getRun(id)
      const idx = runs.value.findIndex((r) => r.id === id)
      if (idx >= 0) runs.value[idx] = res.data
      currentRun.value = res.data
      if (res.data.status !== 'running') {
        stopPolling()
        const qRes = await evalApi.getQuestions(id)
        questions.value = qRes.data
      }
    } catch { /* keep polling */ }
  }, 2000)
}

async function startEval() {
  if (!projectId.value) return
  starting.value = true
  try {
    const res = await evalApi.createRun({ project_id: projectId.value, sample_size: sampleSize.value })
    ElMessage.success('评测已开始，可在后台运行')
    runs.value = [res.data, ...runs.value]
    currentRun.value = res.data
    questions.value = []
    startPolling(res.data.id)
  } catch { /* handled by interceptor */ }
  finally {
    starting.value = false
  }
}

async function removeRun(id: number) {
  try {
    await ElMessageBox.confirm('确定删除该评测记录吗？', '警告', {
      confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning',
    })
    await evalApi.deleteRun(id)
    runs.value = runs.value.filter((r) => r.id !== id)
    if (currentRun.value?.id === id) {
      stopPolling()
      currentRun.value = null
      questions.value = []
    }
    ElMessage.success('已删除')
  } catch { /* cancelled */ }
}

function resetView() {
  stopPolling()
  currentRun.value = null
  questions.value = []
}

onMounted(() => {
  loadProjects()
  loadRuns()
})
onUnmounted(stopPolling)
</script>

<style scoped>
.eval-page {
  max-width: 900px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.config-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
.sample-field {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sample-label {
  font-size: 13px;
  color: #64748b;
}
.config-hint {
  margin: 14px 0 0;
  font-size: 12.5px;
  color: #64748b;
  line-height: 1.7;
}
.config-hint code {
  background: #f1f5f9;
  padding: 1px 5px;
  border-radius: 4px;
}
.run-card {
  margin-top: 0;
}
.run-title {
  font-weight: 600;
  font-size: 15px;
  margin-bottom: 14px;
}
.run-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.run-title + .run-meta {
  font-size: 12px;
  color: #94a3b8;
}
.run-status-text {
  margin-top: 10px;
  font-size: 13px;
  color: #64748b;
}
.metric-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
}
.metric-box {
  background: #f8fafc;
  border-radius: 10px;
  padding: 16px 10px;
  text-align: center;
}
.metric-num {
  font-size: 22px;
  font-weight: 700;
  color: #3b82f6;
}
.metric-label {
  margin-top: 4px;
  font-size: 13px;
  color: #334155;
  font-weight: 500;
}
.metric-desc {
  margin-top: 4px;
  font-size: 11px;
  color: #94a3b8;
}
.q-detail {
  padding: 8px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.q-detail-block {
  background: #f8fafc;
  border-radius: 8px;
  padding: 10px 12px;
}
.q-detail-label {
  font-size: 12px;
  color: #3b82f6;
  font-weight: 600;
  margin-bottom: 6px;
}
.q-detail-body {
  font-size: 13px;
  color: #334155;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
.text-muted {
  color: #94a3b8;
}
.history-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 8px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}
.history-row:hover {
  background: #f8fafc;
}
.history-icon {
  color: #94a3b8;
}
.history-proj {
  font-weight: 500;
  color: #334155;
  min-width: 120px;
}
.history-meta {
  font-size: 12px;
  color: #94a3b8;
  flex: 1;
}
.history-del {
  flex-shrink: 0;
}
</style>
