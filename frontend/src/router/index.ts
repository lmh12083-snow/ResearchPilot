import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  // ── Public routes ──
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/Register.vue'),
    meta: { requiresAuth: false },
  },

  // ── Authenticated routes (wrapped in AppLayout) ──
  {
    path: '/',
    component: () => import('@/components/AppLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: { name: 'Dashboard' } },
      { path: 'dashboard', name: 'Dashboard', component: () => import('@/views/Dashboard.vue') },
      { path: 'projects', name: 'Projects', component: () => import('@/views/Projects.vue') },
      { path: 'project/:id', name: 'ProjectDetail', component: () => import('@/views/ProjectDetail.vue') },
      { path: 'settings', name: 'Settings', component: () => import('@/views/Settings.vue') },
      { path: 'upload', name: 'Upload', component: () => import('@/views/UploadPaper.vue') },
      { path: 'eval', name: 'Eval', component: () => import('@/views/Eval.vue') },
      { path: 'paper/:id', name: 'PaperReading', component: () => import('@/views/PaperReading.vue') },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Navigation guard
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')
  if (to.meta.requiresAuth && !token) {
    next('/login')
  } else {
    next()
  }
})

export default router
