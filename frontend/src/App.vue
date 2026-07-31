<template>
  <router-view />
</template>

<script setup lang="ts">
</script>

<style>
*,
*::before,
*::after {
  box-sizing: border-box;
}

body {
  margin: 0;
  padding: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial,
    'Noto Sans', 'Noto Sans CJK SC', sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background: #f0f2f5;
  color: #1a1a2e;
}

/* Custom scrollbar */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: #c1c7cd;
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: #a8adb3;
}

/* Link reset */
a {
  color: #3b82f6;
  text-decoration: none;
}
a:hover {
  color: #2563eb;
}

/* Element Plus overrides */
.el-card {
  border-radius: 12px !important;
  border: 1px solid #e8eaed !important;
}

.el-table {
  border-radius: 12px;
  overflow: hidden;
}

.el-button--primary {
  background: linear-gradient(135deg, #3b82f6, #6366f1) !important;
  border: none !important;
}
.el-button--primary:hover {
  background: linear-gradient(135deg, #2563eb, #4f46e5) !important;
}
.el-button--primary.is-loading {
  background: linear-gradient(135deg, #3b82f6, #6366f1) !important;
}

.el-dialog {
  border-radius: 16px !important;
}

.el-dialog__header {
  border-bottom: 1px solid #e8eaed;
  padding: 20px 24px !important;
  margin-right: 0 !important;
}

.el-dialog__body {
  padding: 24px !important;
}

.el-dialog__footer {
  border-top: 1px solid #e8eaed;
  padding: 16px 24px !important;
}

.el-tag--success {
  background: #ecfdf5 !important;
  color: #059669 !important;
  border: 1px solid #a7f3d0 !important;
}
.el-tag--danger {
  background: #fef2f2 !important;
  color: #dc2626 !important;
  border: 1px solid #fecaca !important;
}
.el-tag--warning {
  background: #fffbeb !important;
  color: #d97706 !important;
  border: 1px solid #fde68a !important;
}
.el-tag--primary {
  background: #eff6ff !important;
  color: #2563eb !important;
  border: 1px solid #bfdbfe !important;
}
</style>
