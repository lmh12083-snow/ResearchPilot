<template>
  <div class="dashboard">
    <!-- Welcome -->
    <el-card class="welcome-card">
      <h3>👋 欢迎回来，{{ userStore.user?.username || '用户' }}！</h3>
      <p class="welcome-sub">继续你的研究之旅</p>
    </el-card>

    <!-- Stats -->
    <el-row :gutter="20" class="stats-row">
      <el-col :span="12">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-inner">
            <div class="stat-icon stat-icon--project">
              <FolderOpened />
            </div>
            <div>
              <div class="stat-value">{{ data?.project_count ?? '-' }}</div>
              <div class="stat-label">项目总数</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-inner">
            <div class="stat-icon stat-icon--paper">
              <Document />
            </div>
            <div>
              <div class="stat-value">{{ data?.paper_count ?? '-' }}</div>
              <div class="stat-label">论文总数</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Recent Activity -->
    <el-row :gutter="20">
      <el-col :span="12">
        <el-card class="activity-card" shadow="hover">
          <template #header>
            <div class="activity-header">
              <span>最近上传论文</span>
              <el-button text type="primary" size="small" @click="router.push('/upload')">上传</el-button>
            </div>
          </template>
          <div v-if="data?.recent_papers?.length">
            <div v-for="p in data.recent_papers" :key="p.id" class="activity-item">
              <div class="activity-title">
                <router-link :to="`/project/${p.project_id}`">{{ p.title }}</router-link>
              </div>
              <div class="activity-meta">
                <span class="activity-project">{{ p.project_name }}</span>
                <el-tag :type="statusType(p.status)" size="small">{{ statusLabel(p.status) }}</el-tag>
              </div>
            </div>
          </div>
          <el-empty v-else description="暂无上传记录" :image-size="50" />
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card class="activity-card" shadow="hover">
          <template #header>
            <div class="activity-header">
              <span>最近项目</span>
              <el-button text type="primary" size="small" @click="router.push('/projects')">查看全部</el-button>
            </div>
          </template>
          <div v-if="data?.recent_projects?.length">
            <div v-for="p in data.recent_projects" :key="p.id" class="activity-item">
              <div class="activity-title">
                <router-link :to="`/project/${p.id}`">{{ p.name }}</router-link>
              </div>
              <div class="activity-meta">{{ p.paper_count }} 篇论文</div>
            </div>
          </div>
          <el-empty v-else description="暂无项目" :image-size="50" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { dashboardApi } from '@/api/dashboard'
import type { DashboardData } from '@/api/dashboard'
import { FolderOpened, Document } from '@element-plus/icons-vue'

const router = useRouter()
const userStore = useUserStore()
const data = ref<DashboardData | null>(null)

async function fetchDashboard() {
  try {
    const res = await dashboardApi.get()
    data.value = res.data
  } catch {
    // handled by interceptor
  }
}

function statusType(status: string): 'warning' | 'primary' | 'success' | 'danger' | 'info' {
  switch (status) {
    case 'UPLOADING':
    case 'PENDING':
      return 'warning'
    case 'PARSING':
    case 'CHUNKING':
    case 'EMBEDDING':
    case 'INDEXING':
      return 'primary'
    case 'COMPLETED':
      return 'success'
    case 'FAILED':
      return 'danger'
    default:
      return 'info'
  }
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    UPLOADING: '上传中',
    PENDING: '待处理',
    PARSING: '解析中',
    CHUNKING: '分块中',
    EMBEDDING: '向量化',
    INDEXING: '建立索引',
    COMPLETED: '已完成',
    FAILED: '失败',
  }
  return map[status] || status
}

onMounted(fetchDashboard)
</script>

<style scoped>
.dashboard {
  max-width: 960px;
}

.welcome-card {
  margin-bottom: 20px;
}
.welcome-card h3 {
  margin: 0 0 4px;
  font-size: 18px;
}
.welcome-sub {
  margin: 0;
  color: #94a3b8;
  font-size: 14px;
}

.stats-row {
  margin-bottom: 20px;
}

.stat-inner {
  display: flex;
  align-items: center;
  gap: 16px;
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  flex-shrink: 0;
}
.stat-icon--project {
  background: #eff6ff;
  color: #3b82f6;
}
.stat-icon--paper {
  background: #faf5ff;
  color: #8b5cf6;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #1e293b;
  line-height: 1.2;
}
.stat-label {
  font-size: 13px;
  color: #94a3b8;
  margin-top: 2px;
}

.activity-card {
  margin-bottom: 20px;
}
.activity-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.activity-item {
  padding: 10px 0;
  border-bottom: 1px solid #f1f5f9;
}
.activity-item:last-child {
  border-bottom: none;
}
.activity-title {
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 4px;
}
.activity-title a {
  color: #1e293b;
}
.activity-title a:hover {
  color: #3b82f6;
}
.activity-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #94a3b8;
}
.activity-project {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
