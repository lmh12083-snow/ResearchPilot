<template>
  <div class="settings-page">
    <!-- 头像 -->
    <el-card shadow="hover">
      <template #header><span class="card-title">头像设置</span></template>
      <div class="avatar-row">
        <el-avatar :size="72" :src="avatarSrc" :icon="avatarSrc ? undefined : UserFilled" />
        <div class="avatar-actions">
          <el-upload
            :show-file-list="false"
            :before-upload="handleAvatarUpload"
            accept="image/png,image/jpeg,image/webp,image/gif"
          >
            <el-button type="primary" :loading="uploadingAvatar">上传新头像</el-button>
          </el-upload>
          <el-button v-if="userStore.user?.avatar" :loading="deletingAvatar" @click="handleAvatarDelete">
            移除头像
          </el-button>
          <p class="avatar-hint">支持 png / jpg / webp / gif，不超过 2MB</p>
        </div>
      </div>
    </el-card>

    <!-- 基本信息 -->
    <el-card shadow="hover">
      <template #header><span class="card-title">基本信息</span></template>
      <el-form label-width="70px" :model="profileForm" @submit.prevent>
        <el-form-item label="用户名">
          <el-input v-model="profileForm.username" placeholder="用户名" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="profileForm.email" placeholder="邮箱" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="savingProfile" @click="saveProfile">保存</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 修改密码 -->
    <el-card shadow="hover">
      <template #header><span class="card-title">修改密码</span></template>
      <el-form label-width="70px" :model="pwdForm" @submit.prevent>
        <el-form-item label="当前密码">
          <el-input v-model="pwdForm.old_password" type="password" show-password placeholder="当前密码" />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input v-model="pwdForm.confirm" type="password" show-password placeholder="再次输入新密码" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="savingPwd" @click="savePassword">保存</el-button>
        </el-form-item>
      </el-form>
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
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { Refresh, UserFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { userApi } from '@/api/user'
import { llmApi, type LLMStats } from '@/api/llm'

const userStore = useUserStore()

// ── 头像 ────────────────────────────────────────────────────────
const uploadingAvatar = ref(false)
const deletingAvatar = ref(false)

const avatarSrc = computed(() =>
  userStore.user?.avatar ? userApi.getAvatarUrl() : '',
)

async function handleAvatarUpload(file: File): Promise<boolean> {
  uploadingAvatar.value = true
  try {
    const res = await userApi.uploadAvatar(file)
    userStore.setUser(res.data)
    ElMessage.success('头像已更新')
  } catch { /* handled by interceptor */ }
  finally {
    uploadingAvatar.value = false
  }
  return false
}

async function handleAvatarDelete() {
  deletingAvatar.value = true
  try {
    const res = await userApi.deleteAvatar()
    userStore.setUser(res.data)
    ElMessage.success('已移除头像')
  } catch { /* handled by interceptor */ }
  finally {
    deletingAvatar.value = false
  }
}

// ── 基本信息 ───────────────────────────────────────────────────
const profileForm = reactive({ username: '', email: '' })
const savingProfile = ref(false)

watch(
  () => userStore.user,
  (u) => {
    if (u) {
      profileForm.username = u.username
      profileForm.email = u.email
    }
  },
  { immediate: true },
)

async function saveProfile() {
  const payload: { username?: string; email?: string } = {}
  if (profileForm.username && profileForm.username !== userStore.user?.username) {
    payload.username = profileForm.username
  }
  if (profileForm.email && profileForm.email !== userStore.user?.email) {
    payload.email = profileForm.email
  }
  if (!Object.keys(payload).length) {
    ElMessage.info('没有需要修改的内容')
    return
  }
  savingProfile.value = true
  try {
    const res = await userApi.updateProfile(payload)
    userStore.setUser(res.data)
    ElMessage.success('保存成功')
  } catch { /* handled by interceptor */ }
  finally {
    savingProfile.value = false
  }
}

// ── 修改密码 ───────────────────────────────────────────────────
const pwdForm = reactive({ old_password: '', new_password: '', confirm: '' })
const savingPwd = ref(false)

async function savePassword() {
  if (pwdForm.new_password.length < 6) {
    ElMessage.warning('新密码至少 6 位')
    return
  }
  if (pwdForm.new_password !== pwdForm.confirm) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  savingPwd.value = true
  try {
    await userApi.changePassword({
      old_password: pwdForm.old_password,
      new_password: pwdForm.new_password,
    })
    ElMessage.success('密码已修改')
    pwdForm.old_password = ''
    pwdForm.new_password = ''
    pwdForm.confirm = ''
  } catch { /* handled by interceptor */ }
  finally {
    savingPwd.value = false
  }
}

// ── LLM 用量统计 ──────────────────────────────────────────────
const stats = ref<LLMStats | null>(null)
const loading = ref(false)

const FEATURE_LABELS: Record<string, string> = {
  chat: '对话',
  agent: 'Agent 工具调用',
  analysis: '论文分析',
  eval: 'RAG 评测',
  notes: '阅读笔记提炼',
  compare: '论文对比',
  compare_planner: '对比·规划维度',
  compare_specialist: '对比·论文分析',
  compare_aggregate: '对比·聚合',
  review_planner: '综述·结构规划',
  review_section: '综述·章节撰写',
  review_intro: '综述·摘要概述',
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
.card-title {
  font-weight: 600;
  font-size: 16px;
}
.avatar-row {
  display: flex;
  align-items: center;
  gap: 24px;
}
.avatar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.avatar-hint {
  width: 100%;
  margin: 0;
  font-size: 12px;
  color: #94a3b8;
}
.usage-card {
  margin-top: 8px;
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
