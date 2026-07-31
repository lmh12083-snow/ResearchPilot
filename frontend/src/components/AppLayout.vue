<template>
  <div class="layout">
    <!-- Left sidebar navigation -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="avatar">{{ userInitial }}</div>
        <div class="user-name">{{ userStore.user?.username || 'User' }}</div>
      </div>

      <el-menu
        :default-active="activeRoute"
        class="sidebar-menu"
        text-color="rgba(255,255,255,0.65)"
        active-text-color="#fff"
        @select="navigate"
      >
        <el-menu-item index="/dashboard">
          <el-icon><Grid /></el-icon>
          <span>仪表盘</span>
        </el-menu-item>
        <el-menu-item index="/projects">
          <el-icon><FolderOpened /></el-icon>
          <span>项目列表</span>
        </el-menu-item>
        <el-menu-item index="/upload">
          <el-icon><Upload /></el-icon>
          <span>上传论文</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>设置</span>
        </el-menu-item>
      </el-menu>

      <div class="sidebar-footer">
        <div class="logout-btn" @click="handleLogout">
          <el-icon><SwitchButton /></el-icon>
          <span>退出登录</span>
        </div>
      </div>
    </aside>

    <!-- Main content area -->
    <div class="main-area">
      <div class="top-bar">
        <h2 class="brand">ResearchPilot</h2>
      </div>
      <div class="content-wrapper">
        <router-view />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { userApi } from '@/api/user'
import { Grid, FolderOpened, Upload, Setting, SwitchButton } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const activeRoute = computed(() => {
  // Highlight parent route for sub-routes like /project/:id, /paper/:id
  const path = route.path
  if (path.startsWith('/project')) return '/projects'
  if (path.startsWith('/paper')) return '/upload'
  return path
})

const userInitial = computed(() => {
  return (userStore.user?.username || 'U').charAt(0).toUpperCase()
})

function navigate(index: string) {
  router.push(index)
}

async function handleLogout() {
  try { await userApi.logout() } catch { /* v1 stateless */ }
  userStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.layout {
  display: flex;
  min-height: 100vh;
  background: #f0f2f5;
}

/* ── Main Area ── */
.main-area {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.top-bar {
  height: 56px;
  display: flex;
  align-items: center;
  padding: 0 32px;
  background: #fff;
  border-bottom: 1px solid #e8eaed;
  flex-shrink: 0;
}

.brand {
  font-size: 18px;
  font-weight: 700;
  margin: 0;
  background: linear-gradient(135deg, #3b82f6, #8b5cf6);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.content-wrapper {
  flex: 1;
  padding: 24px 32px;
  overflow-y: auto;
}

/* ── Sidebar ── */
.sidebar {
  width: 220px;
  background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  height: 100vh;
  border-right: 1px solid rgba(255, 255, 255, 0.06);
}

.sidebar-header {
  padding: 28px 20px 20px;
  text-align: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: linear-gradient(135deg, #3b82f6, #8b5cf6);
  color: #fff;
  font-size: 20px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 10px;
}

.user-name {
  color: #fff;
  font-size: 14px;
  font-weight: 500;
}

/* ── Menu ── */
.sidebar-menu {
  flex: 1;
  padding: 12px 0;
  background: transparent;
  border-right: none;
}

.sidebar-menu .el-menu-item {
  height: 48px;
  line-height: 48px;
  margin: 2px 8px;
  border-radius: 8px;
  font-size: 14px;
}

.sidebar-menu .el-menu-item.is-active {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.3), rgba(139, 92, 246, 0.2));
}

.sidebar-menu .el-menu-item:hover {
  background: rgba(255, 255, 255, 0.06);
}

.sidebar-menu .el-menu-item .el-icon {
  margin-right: 10px;
  font-size: 18px;
}

/* ── Footer ── */
.sidebar-footer {
  padding: 16px 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.logout-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  color: rgba(255, 255, 255, 0.5);
  cursor: pointer;
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 14px;
  transition: all 0.2s;
}

.logout-btn:hover {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}
</style>
