<template>
  <div class="detail-container">
    <el-container>
      <el-header class="header">
        <div class="header-left">
          <el-button text @click="router.push('/projects')">&lt; 返回</el-button>
          <h2>{{ project?.name || '项目详情' }}</h2>
        </div>
        <div class="header-right">
          <el-button type="danger" text @click="handleLogout">退出登录</el-button>
        </div>
      </el-header>
      <el-main>
        <el-card v-if="project">
          <h3>{{ project.name }}</h3>
          <p class="description">{{ project.description || '暂无描述' }}</p>
          <p class="meta">创建时间：{{ project.created_at }}</p>
        </el-card>
        <el-empty v-else description="项目不存在" />
      </el-main>
    </el-container>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { projectApi } from '@/api/project'
import type { Project } from '@/api/project'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const project = ref<Project | null>(null)

async function fetchProject() {
  try {
    const id = Number(route.params.id)
    const res = await projectApi.get(id)
    project.value = res.data
  } catch {
    // handled by interceptor
  }
}

function handleLogout() {
  userStore.logout()
  router.push('/login')
}

onMounted(fetchProject)
</script>

<style scoped>
.detail-container {
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
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.header-left h2 {
  color: #409eff;
}
.description {
  color: #666;
  margin: 16px 0;
}
.meta {
  color: #999;
  font-size: 13px;
}
</style>
