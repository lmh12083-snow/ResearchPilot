<template>
  <div class="projects-container">
    <el-container>
      <el-header class="header">
        <div class="header-left">
          <h2>ResearchPilot</h2>
        </div>
        <div class="header-right">
          <el-button text @click="router.push('/dashboard')">仪表盘</el-button>
          <el-button text @click="router.push('/settings')">设置</el-button>
          <el-button type="danger" text @click="handleLogout">退出登录</el-button>
        </div>
      </el-header>
      <el-main>
        <div class="toolbar">
          <h3>项目列表</h3>
          <el-button type="primary" @click="showCreate = true">新建项目</el-button>
        </div>

        <el-table :data="projects" stripe style="width: 100%">
          <el-table-column prop="name" label="名称" min-width="180" />
          <el-table-column prop="description" label="描述" min-width="300" show-overflow-tooltip />
          <el-table-column prop="created_at" label="创建时间" width="180" />
          <el-table-column label="操作" width="150">
            <template #default="{ row }">
              <el-button type="primary" link @click="router.push(`/project/${row.id}`)">
                查看
              </el-button>
              <el-button type="danger" link @click="handleDelete(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-main>
    </el-container>

    <!-- Create Dialog -->
    <el-dialog v-model="showCreate" title="新建项目" width="500px">
      <el-form ref="formRef" :model="createForm" :rules="rules" label-width="80px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="createForm.name" placeholder="项目名称" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input
            v-model="createForm.description"
            type="textarea"
            :rows="4"
            placeholder="项目描述（可选）"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import { projectApi } from '@/api/project'
import type { Project } from '@/api/project'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

const projects = ref<Project[]>([])
const showCreate = ref(false)
const creating = ref(false)
const formRef = ref<FormInstance>()

const createForm = ref({
  name: '',
  description: '',
})

const rules: FormRules = {
  name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
}

async function fetchProjects() {
  try {
    const res = await projectApi.list()
    projects.value = res.data
  } catch {
    // handled by interceptor
  }
}

async function handleCreate() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  creating.value = true
  try {
    await projectApi.create(createForm.value)
    ElMessage.success('项目创建成功')
    showCreate.value = false
    createForm.value = { name: '', description: '' }
    await fetchProjects()
  } catch {
    // handled by interceptor
  } finally {
    creating.value = false
  }
}

async function handleDelete(id: number) {
  try {
    await ElMessageBox.confirm('确定要删除该项目吗？', '警告', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await projectApi.delete(id)
    ElMessage.success('删除成功')
    await fetchProjects()
  } catch {
    // cancelled or error
  }
}

function handleLogout() {
  userStore.logout()
  router.push('/login')
}

onMounted(fetchProjects)
</script>

<style scoped>
.projects-container {
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
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
</style>
