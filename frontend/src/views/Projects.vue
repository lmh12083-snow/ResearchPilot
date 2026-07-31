<template>
  <div class="projects">
    <div class="page-header">
      <h3>项目列表</h3>
      <el-button type="primary" @click="showCreate = true">+ 新建项目</el-button>
    </div>

    <el-table :data="projects" stripe style="width: 100%">
      <el-table-column prop="name" label="名称" min-width="180" />
      <el-table-column prop="description" label="描述" min-width="300" show-overflow-tooltip />
      <el-table-column prop="paper_count" label="论文数" width="80" align="center" />
      <el-table-column prop="created_at" label="创建时间" width="180" />
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button type="primary" link @click="router.push(`/project/${row.id}`)">查看</el-button>
          <el-button type="danger" link @click="handleDelete(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Create Dialog -->
    <el-dialog v-model="showCreate" title="新建项目" width="500px">
      <el-form ref="formRef" :model="createForm" :rules="rules" label-width="60px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="createForm.name" placeholder="项目名称" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="createForm.description" type="textarea" :rows="4" placeholder="项目描述（可选）" />
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

const router = useRouter()

const projects = ref<Project[]>([])
const showCreate = ref(false)
const creating = ref(false)
const formRef = ref<FormInstance>()

const createForm = ref({ name: '', description: '' })
const rules: FormRules = {
  name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
}

async function fetchProjects() {
  try {
    const res = await projectApi.list()
    projects.value = res.data
  } catch { /* handled by interceptor */ }
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
  } catch { /* handled by interceptor */ }
  finally { creating.value = false }
}

async function handleDelete(id: number) {
  try {
    await ElMessageBox.confirm('确定要删除该项目吗？', '警告', {
      confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning',
    })
    await projectApi.delete(id)
    ElMessage.success('删除成功')
    await fetchProjects()
  } catch { /* cancelled */ }
}

onMounted(fetchProjects)
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.page-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}
</style>
