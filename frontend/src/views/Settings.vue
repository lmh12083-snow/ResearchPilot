<template>
  <div class="settings-page">
    <el-card shadow="hover">
      <template #header>
        <span style="font-weight: 600; font-size: 16px;">用户设置</span>
      </template>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="用户名">
          <div class="info-value">{{ userStore.user?.username }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="邮箱">
          <div class="info-value">{{ userStore.user?.email }}</div>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card shadow="hover" class="usage-card">
      <template #header>
        <div class="usage-header">
          <span style="font-weight: 600; font-size: 16px;">LLM 用量统计</span>
          <el-button size="small" text @click="loadStats">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </template>

      <div v-if="stats" class="usage-grid">
        <div class="stat-box">
          <div class="stat-num">{{ stats.today_calls }}</div>
          <div class="stat-label">今日调用</div>
        </div>
        <div class="stat-box">
          <div class="stat-num">{{ stats.today_tokens.toLocaleString() }}</div>
          <div class="stat-label">今日 Tokens</div>
        </div>
        <div class="stat-box">
          <div class="stat-num">{{ stats.total_calls }}</div>
          <div class="stat-label">累计调用</div>
        </div>
        <div class="stat-box">
          <div class="stat-num">{{ stats.total_tokens.toLocaleString() }}</div>
          <div class="stat-label">累计 Tokens</div>
        </div>
      </div>

      <el-divider v-if="stats && stats.by_feature.length" />

      <div v-if="stats && stats.by_feature.length" class="feature-list">
        <div v-for="f in stats.by_feature" :key="f.feature" class="feature-row">
          <span class="feature-name">{{ FEATURE_LABELS[f.feature] || f.feature }}</span>
          <el-progress
            class="feature-bar"
            :percentage="pctOfTotal(f.total_tokens)"
            :stroke-width="8"
          />
          <span class="feature-tokens">{{ f.total_tokens.toLocaleString() }} tok / {{ f.calls }} 次</span>
        </div>
      </div>

      <div v-else-if="!loading" class="usage-empty">暂无 LLM 调用记录</div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { llmApi, type LLMStats } from '@/api/llm'

const userStore = useUserStore()
const stats = ref<LLMStats | null>(null)
const loading = ref(false)

const FEATURE_LABELS: Record<string, string> = {
  chat: '对话',
  agent: 'Agent 工具调用',
  analysis: '论文分析',
  eval: 'RAG 评测',
}

function pctOfTotal(tokens: number): number {
  if (!stats.value || stats.value.total_tokens === 0) return 0
  return Math.round((tokens / stats.value.total_tokens) * 100)
}

async function loadStats() {
  loading.value = true
  try {
    const res = await llmApi.stats()
    stats.value = res.data
  } finally {
    loading.value = false
  }
}

onMounted(loadStats)
</script>

<style scoped>
.settings-page {
  max-width: 700px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.info-value {
  color: #1e293b;
  font-weight: 500;
}
.usage-card {
  margin-top: 16px;
}
.usage-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.usage-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.stat-box {
  background: #f8fafc;
  border-radius: 10px;
  padding: 16px 12px;
  text-align: center;
}
.stat-num {
  font-size: 22px;
  font-weight: 700;
  color: #3b82f6;
}
.stat-label {
  margin-top: 6px;
  font-size: 12px;
  color: #64748b;
}
.feature-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.feature-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.feature-name {
  width: 110px;
  font-size: 13px;
  color: #334155;
  flex-shrink: 0;
}
.feature-bar {
  flex: 1;
}
.feature-tokens {
  font-size: 12px;
  color: #64748b;
  flex-shrink: 0;
  min-width: 140px;
  text-align: right;
}
.usage-empty {
  color: #94a3b8;
  font-size: 13px;
  text-align: center;
  padding: 12px 0;
}
</style>
