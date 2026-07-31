<template>
  <div class="auth-page">
    <div class="auth-bg" />
    <el-card class="auth-card" shadow="always">
      <div class="auth-header">
        <div class="auth-logo">RP</div>
        <h2>ResearchPilot</h2>
        <p class="auth-sub">学术论文管理平台</p>
      </div>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="0" size="large" @keyup.enter="handleLogin">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" show-password prefix-icon="Lock" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" class="submit-btn" @click="handleLogin">登录</el-button>
        </el-form-item>
      </el-form>
      <div class="auth-footer">
        还没有账号？<router-link to="/register">立即注册</router-link>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { userApi } from '@/api/user'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()
const formRef = ref<FormInstance>()
const loading = ref(false)

const form = reactive({ username: '', password: '' })
const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    const res = await userApi.login(form)
    userStore.setToken(res.data.access_token)
    userStore.setUser(res.data.user)
    ElMessage.success('登录成功')
    router.push('/dashboard')
  } catch { /* handled by interceptor */ }
  finally { loading.value = false }
}
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0f172a;
  position: relative;
  overflow: hidden;
}

.auth-bg {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse at 20% 50%, rgba(59, 130, 246, 0.15) 0%, transparent 60%),
    radial-gradient(ellipse at 80% 50%, rgba(139, 92, 246, 0.15) 0%, transparent 60%);
}

.auth-card {
  width: 400px;
  position: relative;
  border-radius: 16px !important;
  padding: 8px;
}

.auth-header {
  text-align: center;
  margin-bottom: 28px;
}

.auth-logo {
  width: 56px;
  height: 56px;
  border-radius: 16px;
  background: linear-gradient(135deg, #3b82f6, #8b5cf6);
  color: #fff;
  font-size: 22px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
}

.auth-header h2 {
  margin: 0 0 6px;
  font-size: 22px;
  color: #1e293b;
}

.auth-sub {
  margin: 0;
  color: #94a3b8;
  font-size: 14px;
}

.submit-btn { width: 100%; }

.auth-footer {
  text-align: center;
  font-size: 14px;
  color: #64748b;
}
.auth-footer a { color: #3b82f6; font-weight: 500; }
</style>
