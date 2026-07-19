<template>
  <div class="settings-container">
    <el-container>
      <el-header class="header">
        <div class="header-left">
          <h2>ResearchPilot</h2>
        </div>
        <div class="header-right">
          <el-button text @click="router.push('/dashboard')">仪表盘</el-button>
          <el-button text @click="router.push('/projects')">项目列表</el-button>
          <el-button type="danger" text @click="handleLogout">退出登录</el-button>
        </div>
      </el-header>
      <el-main>
        <el-card>
          <h3>用户设置</h3>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="用户名">{{ userStore.user?.username }}</el-descriptions-item>
            <el-descriptions-item label="邮箱">{{ userStore.user?.email }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-main>
    </el-container>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

function handleLogout() {
  userStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.settings-container {
  min-height: 100vh;
  background: #f5f7fa;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
}
.header-left h2 {
  color: #409eff;
}
</style>
