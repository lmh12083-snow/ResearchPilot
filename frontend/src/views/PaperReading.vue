<template>
  <div class="reading-page">
    <!-- Loading -->
    <div v-if="loading" class="center-state">
      <el-skeleton :rows="20" animated />
    </div>

    <!-- Not Found -->
    <el-result v-else-if="notFound" icon="warning" title="论文未找到" sub-title="该论文不存在或已被删除。">
      <template #extra>
        <el-button type="primary" @click="router.push('/projects')">返回项目列表</el-button>
      </template>
    </el-result>

    <!-- Error -->
    <el-result v-else-if="error" icon="error" title="加载失败" sub-title="加载论文内容时发生错误。">
      <template #extra>
        <el-button @click="goBack">返回</el-button>
        <el-button type="primary" @click="loadAll">重试</el-button>
      </template>
    </el-result>

    <!-- Main Content -->
    <template v-else-if="paperDetail">
      <div class="reading-split">
        <!-- ── Left Panel: PDF / Text ── -->
        <div class="left-panel">
          <div class="panel-header">
            <el-button text @click="goBack">← 返回</el-button>
            <div class="panel-header-info">
              <h2 class="paper-title">{{ paperDetail.title }}</h2>
              <div class="paper-meta">
                <el-tag :type="statusTagType" size="small">{{ statusLabel }}</el-tag>
                <span v-if="paperDetail.authors" class="meta-item">作者：{{ parseAuthors(paperDetail.authors) }}</span>
                <span v-if="paperDetail.year" class="meta-item">年份：{{ paperDetail.year }}</span>
                <span v-if="paperContent?.page_count" class="meta-item">页数：{{ paperContent.page_count }}</span>
              </div>
            </div>
          </div>

          <el-tabs v-model="viewMode" class="view-tabs">
            <el-tab-pane label="PDF 原文" name="pdf">
              <div class="pdf-viewer" v-loading="pdfLoading">
                <iframe
                  v-if="pdfUrl"
                  :src="pdfUrl"
                  class="pdf-iframe"
                  frameborder="0"
                  @load="pdfLoading = false"
                />
              </div>
            </el-tab-pane>
            <el-tab-pane label="提取文本" name="text">
              <div class="text-viewer" v-if="paperContent?.text" @mouseup="captureSelection">
                <pre class="parsed-text">{{ paperContent.text }}</pre>
              </div>
              <el-empty v-else description="暂无提取文本" :image-size="60" />
            </el-tab-pane>
          </el-tabs>
        </div>

        <!-- ── Right Panel: Analysis / Chat ── -->
        <div class="right-panel">
          <el-tabs v-model="rightTab" class="right-tabs">
            <!-- ═══ Analysis Tab ═══ -->
            <el-tab-pane label="分析" name="analysis">
              <div class="analysis-panel">
                <template v-if="analysisLoading">
                  <div class="analysis-loading">
                    <el-icon class="is-loading" :size="18" color="#3b82f6"><Loading /></el-icon>
                    <span>多 Agent 正在并行分析论文（创新点 / 方法 / 实验 / 局限 / 相关工作）…</span>
                  </div>
                  <el-skeleton :rows="6" animated />
                </template>

                <div v-else-if="analysisError" class="analysis-empty">
                  <el-icon :size="32" color="#94a3b8"><WarningFilled /></el-icon>
                  <p>分析暂不可用</p>
                  <el-button size="small" @click="loadAnalysis">重试</el-button>
                </div>

                <div v-else-if="analysisData" class="analysis-content">
                  <!-- One-sentence summary -->
                  <div v-if="analysisData.one_sentence" class="one-sentence">
                    <el-icon :size="18" color="#3b82f6"><StarFilled /></el-icon>
                    <span>{{ analysisData.one_sentence }}</span>
                  </div>

                  <!-- Collapsible Sections -->
                  <el-collapse v-model="openSections" class="analysis-collapse">
                    <el-collapse-item title="📄 摘要" name="abstract">
                      <div class="section-content">{{ analysisData.abstract || '暂无' }}</div>
                    </el-collapse-item>

                    <el-collapse-item title="💡 创新点" name="innovation">
                      <div class="section-content" v-html="renderList(analysisData.innovation)"></div>
                    </el-collapse-item>

                    <el-collapse-item title="🔬 研究方法" name="methods">
                      <div class="section-content">{{ analysisData.methods || '暂无' }}</div>
                    </el-collapse-item>

                    <el-collapse-item title="📊 实验设计" name="experiments">
                      <div class="section-content">{{ analysisData.experiments || '暂无' }}</div>
                    </el-collapse-item>

                    <el-collapse-item title="⚠️ 局限性" name="limitations">
                      <div class="section-content" v-html="renderList(analysisData.limitations)"></div>
                    </el-collapse-item>

                    <el-collapse-item title="🔗 相关工作" name="related_work">
                      <div class="section-content">{{ analysisData.related_work || '暂无' }}</div>
                    </el-collapse-item>

                    <el-collapse-item title="⚖️ 优缺点" name="pros_cons">
                      <div class="section-content" v-html="renderList(analysisData.pros_cons)"></div>
                    </el-collapse-item>

                  </el-collapse>

                  <div class="analysis-actions">
                    <el-button size="small" :loading="regenerating" @click="regenerateAnalysis">
                      <el-icon><Refresh /></el-icon> 重新生成分析
                    </el-button>
                  </div>
                </div>

                <div v-else class="analysis-empty">
                  <el-icon :size="32" color="#94a3b8"><InfoFilled /></el-icon>
                  <p>暂无分析，请先上传并处理论文</p>
                </div>
              </div>
            </el-tab-pane>

            <!-- ═══ Chat Tab ═══ -->
            <el-tab-pane label="对话" name="chat">
              <div class="chat-panel">
                <!-- Quick Actions -->
                <div class="quick-actions">
                  <el-button
                    v-for="btn in quickActions"
                    :key="btn.key"
                    size="small"
                    :type="btn.type || 'default'"
                    :disabled="chatSending"
                    @click="sendQuickAction(btn.prompt)"
                  >
                    {{ btn.label }}
                  </el-button>
                </div>

                <el-divider style="margin: 8px 0" />

                <!-- Messages -->
                <div ref="chatMessagesRef" class="chat-messages">
                  <div v-if="chatHistory.length === 0 && !chatSending" class="chat-empty">
                    <el-icon :size="28" color="#94a3b8"><ChatLineRound /></el-icon>
                    <p>选择一个快捷问题开始对话</p>
                  </div>

                  <div
                    v-for="msg in chatHistory"
                    :key="msg.id"
                    class="chat-msg-wrapper"
                  >
                    <div class="chat-msg" :class="msg.role">
                      <div class="msg-avatar">
                        <el-avatar :size="28" :icon="msg.role === 'user' ? UserFilled : Promotion" />
                      </div>
                      <div v-if="msg.role === 'assistant' && !msg.content" class="msg-bubble thinking">
                        <span class="dot-pulse"></span>
                      </div>
                      <div v-else class="msg-bubble" v-html="formatContent(msg.content, msg.role)"></div>
                    </div>

                    <!-- Citations -->
                    <div v-if="msg.role === 'assistant'" class="msg-footer">
                      <template v-if="getMsgMeta(msg.id)">
                        <div v-if="getMsgMeta(msg.id)!.citations.length" class="citation-tags">
                          <el-tag
                            v-for="(c, ci) in getMsgMeta(msg.id)!.citations"
                            :key="ci"
                            size="small"
                            type="info"
                            class="citation-tag"
                          >
                            §{{ c.chunk_index ?? '?' }}<span v-if="c.page_number"> p.{{ c.page_number }}</span>
                          </el-tag>
                        </div>

                        <!-- Suggestion buttons when no answer found -->
                        <div v-if="!getMsgMeta(msg.id)!.hasAnswer" class="suggestion-buttons">
                          <el-button size="small" type="primary" plain @click="sendMessage(msg.content)">
                            ✓ 仅基于当前论文回答
                          </el-button>
                          <el-button size="small" type="success" plain @click="sendWithMode('project_search', msg.content)">
                            🔍 在当前 Project 中继续检索
                          </el-button>
                          <el-button size="small" type="warning" plain @click="sendWithMode('web_search', msg.content)">
                            🌐 查找相关最新论文（Beta）
                          </el-button>
                        </div>
                      </template>
                    </div>
                  </div>

                </div>

                <!-- Mode Selector + Input -->
                <div class="chat-input-area">
                  <div class="chat-mode-selector">
                    <el-radio-group v-model="chatMode" size="small">
                      <el-radio-button value="paper_only">📄 论文检索</el-radio-button>
                      <el-radio-button value="project_search">📚 项目检索</el-radio-button>
                      <el-radio-button value="web_search">🌐 联网搜索</el-radio-button>
                      <el-radio-button value="auto">🤖 智能检索</el-radio-button>
                    </el-radio-group>
                  </div>
                  <div v-if="chatSending && streamStatus" class="stream-status">{{ streamStatus }}</div>
                  <div class="chat-input-bar">
                    <el-input
                      v-model="chatInput"
                      :placeholder="inputPlaceholder"
                      :disabled="chatSending"
                      @keyup.enter="sendMessage()"
                    >
                      <template #append>
                        <el-button v-if="chatSending" @click="stopStream">停止</el-button>
                        <el-button v-else :disabled="!chatInput.trim()" @click="sendMessage">
                          发送
                        </el-button>
                      </template>
                    </el-input>
                  </div>
                </div>
              </div>
            </el-tab-pane>

            <!-- ═══ Notes Tab ═══ -->
            <el-tab-pane label="笔记" name="notes">
              <div class="notes-panel">
                <div class="notes-header">
                  <span class="notes-count">共 {{ notes.length }} 条笔记</span>
                  <el-button size="small" :loading="exportingNotes" @click="exportNotes">
                    导出 Markdown
                  </el-button>
                </div>

                <!-- Compose -->
                <div class="note-compose">
                  <div class="note-compose-row">
                    <el-button
                      size="small"
                      :disabled="!selectedText"
                      @click="noteAnchor = selectedText || noteAnchor"
                    >使用选中文本</el-button>
                    <span v-if="selectedText" class="sel-hint">已选中 {{ selectedText.length }} 字</span>
                  </div>
                  <el-input
                    v-model="noteAnchor"
                    type="textarea"
                    :rows="2"
                    placeholder="摘录片段（切换到「提取文本」选中文字后导入）"
                  />
                  <el-input
                    v-model="noteContent"
                    type="textarea"
                    :rows="2"
                    placeholder="你的笔记 / 想法"
                  />
                  <div class="note-compose-row">
                    <el-input v-model="noteTags" placeholder="标签，用逗号分隔" size="small" style="flex: 1" />
                    <el-checkbox v-model="noteSummarize">AI 提炼</el-checkbox>
                    <el-button
                      type="primary"
                      size="small"
                      :loading="savingNote"
                      :disabled="!noteAnchor && !noteContent"
                      @click="saveNote"
                    >添加</el-button>
                  </div>
                </div>

                <!-- List -->
                <div v-if="notes.length" class="note-list">
                  <div v-for="n in notes" :key="n.id" class="note-item">
                    <div v-if="editingId === n.id" class="note-edit">
                      <el-input v-model="editAnchor" type="textarea" :rows="2" placeholder="摘录" />
                      <el-input v-model="editContent" type="textarea" :rows="2" placeholder="笔记内容" />
                      <div class="note-item-actions">
                        <el-button size="small" type="primary" :loading="savingNote" @click="saveEdit(n)">保存</el-button>
                        <el-button size="small" @click="editingId = null">取消</el-button>
                      </div>
                    </div>
                    <template v-else>
                      <div class="note-item-header">
                        <div class="note-tags">
                          <el-tag v-for="t in n.tags" :key="t" size="small" type="info">{{ t }}</el-tag>
                        </div>
                        <div class="note-item-actions">
                          <el-button size="small" text :loading="summarizingId === n.id" @click="doSummarize(n.id)">AI 提炼</el-button>
                          <el-button size="small" text @click="startEdit(n)">编辑</el-button>
                          <el-button size="small" text type="danger" @click="deleteNote(n.id)">删除</el-button>
                        </div>
                      </div>
                      <div v-if="n.anchor_text" class="note-anchor">“{{ n.anchor_text }}”</div>
                      <div v-if="n.content" class="note-content">{{ n.content }}</div>
                      <div v-if="n.ai_summary" class="note-summary">
                        <span class="summary-label">AI 提炼：</span>
                        <span class="summary-text">{{ n.ai_summary }}</span>
                      </div>
                    </template>
                  </div>
                </div>
                <el-empty v-else description="暂无笔记，记录你的阅读想法" :image-size="60" />
              </div>
            </el-tab-pane>
          </el-tabs>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  StarFilled,
  WarningFilled,
  InfoFilled,
  Refresh,
  Loading,
  ChatLineRound,
  UserFilled,
  Promotion,
} from '@element-plus/icons-vue'
import { paperApi } from '@/api/paper'
import type { Paper, PaperContent, Analysis, ChatMessage, Citation } from '@/api/paper'
import { noteApi, type Note } from '@/api/notes'

// ── Route ──
const route = useRoute()
const router = useRouter()
const paperId = computed(() => Number(route.params.id))

// ── Data ──
const paperDetail = ref<Paper | null>(null)
const paperContent = ref<PaperContent | null>(null)
const loading = ref(true)
const error = ref(false)
const notFound = ref(false)
const pdfLoading = ref(true)

const viewMode = ref<'pdf' | 'text'>('pdf')
const rightTab = ref<'analysis' | 'chat' | 'notes'>('analysis')

// Analysis
const analysisData = ref<Analysis | null>(null)
const analysisLoading = ref(false)
const analysisError = ref(false)
const regenerating = ref(false)
const openSections = ref<string[]>(['abstract', 'innovation', 'methods'])

// Chat
const chatHistory = ref<ChatMessage[]>([])
const chatInput = ref('')
const chatMode = ref<'paper_only' | 'project_search' | 'web_search' | 'auto'>('paper_only')
const chatSending = ref(false)
const streamStatus = ref('')

const inputPlaceholder = computed(() => {
  const map: Record<string, string> = {
    paper_only: '基于当前论文进行提问...',
    project_search: '在整个项目中搜索相关内容...',
    web_search: '联网搜索最新论文信息...',
    auto: '让 Agent 自主检索回答...',
  }
  return map[chatMode.value] || '输入问题...'
})
const chatMessagesRef = ref<HTMLElement | null>(null)
const chatResponseMeta = ref<Map<number, { citations: Citation[], hasAnswer: boolean, suggestions: string[] }>>(new Map())

function getMsgMeta(msgId: number) {
  return chatResponseMeta.value.get(msgId)
}

const quickActions = [
  { key: 'summary', label: '📝 总结论文', prompt: '请用中文总结这篇论文的核心内容' },
  { key: 'methods', label: '🔬 研究方法', prompt: '这篇论文使用了哪些研究方法？', type: 'success' },
  { key: 'innovation', label: '💡 创新点', prompt: '这篇论文的主要创新点是什么？', type: 'warning' },
  { key: 'experiments', label: '📊 实验设计', prompt: '请介绍论文的实验设计和评估方法' },
  { key: 'pros_cons', label: '⚖️ 优缺点', prompt: '这篇论文的优缺点是什么？', type: 'danger' },
  { key: 'related', label: '🔗 相关工作', prompt: '论文中提到了哪些相关工作？' },
  { key: 'oneshot', label: '✨ 一句话总结', prompt: '用一句话总结这篇论文', type: 'success' },
]

// ── Computed ──
const pdfUrl = computed(() => {
  if (!paperDetail.value) return ''
  const token = localStorage.getItem('token') || ''
  return `/api/v1/papers/${paperId.value}/file?token=${encodeURIComponent(token)}`
})

const statusTagType = computed(() => {
  if (!paperDetail.value) return 'info'
  const map: Record<string, 'success' | 'danger' | 'warning' | 'primary' | 'info'> = {
    COMPLETED: 'success', FAILED: 'danger',
    UPLOADING: 'warning', PENDING: 'warning',
    PARSING: 'primary', CHUNKING: 'primary',
    EMBEDDING: 'primary', INDEXING: 'primary',
  }
  return map[paperDetail.value.status] || 'info'
})

const statusLabel = computed(() => {
  const map: Record<string, string> = {
    UPLOADING: '上传中', PENDING: '待处理', PARSING: '解析中',
    CHUNKING: '分块中', EMBEDDING: '向量化', INDEXING: '建立索引',
    COMPLETED: '已完成', FAILED: '失败',
  }
  return map[paperDetail.value?.status || ''] || paperDetail.value?.status || ''
})

// ── Helpers ──
function parseAuthors(authors: string | null): string {
  if (!authors) return '—'
  try {
    const parsed = JSON.parse(authors)
    if (Array.isArray(parsed)) return parsed.slice(0, 3).join('; ') + (parsed.length > 3 ? ' et al.' : '')
    return String(parsed)
  } catch {
    return authors
  }
}

function renderList(text: string | null): string {
  if (!text) return '暂无'
  // Convert markdown-like bullet points to HTML
  return text.replace(/^[-*+]\s+/gm, '• ').replace(/\n/g, '<br>')
}

function formatContent(text: string, role: string): string {
  // Only format assistant responses (LLM output may contain **bold**)
  if (role !== 'assistant') return escapeHtml(text)
  let html = escapeHtml(text)
  // Convert **bold** to <strong>
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  return html
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

// ── Load Data ──
async function loadAll() {
  loading.value = true
  error.value = false
  notFound.value = false
  try {
    const [detailRes, contentRes] = await Promise.all([
      paperApi.get(paperId.value),
      paperApi.getContent(paperId.value).catch(() => null),
    ])
    paperDetail.value = detailRes.data
    if (contentRes) paperContent.value = contentRes.data

    // Load analysis, chat and notes in parallel
    loadAnalysis()
    loadChatHistory()
    loadNotes()
  } catch (e: any) {
    if (e?.response?.status === 404) notFound.value = true
    else error.value = true
  } finally {
    loading.value = false
  }
}

async function loadAnalysis() {
  analysisError.value = false
  analysisLoading.value = true
  try {
    const res = await paperApi.getAnalysis(paperId.value)
    analysisData.value = res.data
  } catch {
    analysisError.value = true
  } finally {
    analysisLoading.value = false
  }
}

async function regenerateAnalysis() {
  regenerating.value = true
  try {
    const res = await paperApi.regenerateAnalysis(paperId.value)
    analysisData.value = res.data
    ElMessage.success('分析已重新生成')
  } catch {
    ElMessage.error('重新生成失败')
  } finally {
    regenerating.value = false
  }
}

async function loadChatHistory() {
  try {
    const res = await paperApi.getChatHistory(paperId.value)
    chatHistory.value = res.data
    scrollToBottom()
  } catch { /* ignore */ }
}

async function sendMessage(text?: string) {
  const msg = (text || chatInput.value).trim()
  if (!msg || chatSending.value) return
  // Use the currently selected mode when sending from the input box
  // (suggestion buttons call sendMessage with explicit text, using default mode paper_only)
  await _doSend(msg, text ? 'paper_only' : chatMode.value)
}

function sendWithMode(mode: 'project_search' | 'web_search', text: string) {
  if (chatSending.value) return
  _doSend(text, mode)
}

const activeController = ref<AbortController | null>(null)

function stopStream() {
  activeController.value?.abort()
}

async function _doSend(text: string, mode: string) {
  chatSending.value = true
  const sentText = text
  chatInput.value = ''

  // Optimistically add user message
  const tempUserMsg: ChatMessage = {
    id: -Date.now(),
    paper_id: paperId.value,
    role: 'user',
    content: sentText,
    created_at: new Date().toISOString(),
  }
  chatHistory.value.push(tempUserMsg)

  // Assistant placeholder — content fills in as tokens stream in
  const tempAssistMsg: ChatMessage = {
    id: -Date.now() - 1,
    paper_id: paperId.value,
    role: 'assistant',
    content: '',
    created_at: new Date().toISOString(),
  }
  chatHistory.value.push(tempAssistMsg)
  // Grab the reactive proxy so mutations trigger re-render
  const streamMsg = chatHistory.value[chatHistory.value.length - 1]
  scrollToBottom()

  const controller = new AbortController()
  activeController.value = controller

  try {
    await paperApi.sendChatStream(
      paperId.value,
      { message: sentText, mode: mode as any },
      {
        onMeta: (meta) => {
          chatResponseMeta.value.set(tempAssistMsg.id, {
            citations: meta.citations,
            hasAnswer: meta.has_answer,
            suggestions: meta.suggestions,
          })
        },
        onDelta: (text) => {
          streamMsg.content += text
          if (streamStatus.value) streamStatus.value = ''
          scrollToBottom()
        },
        onStatus: (text) => {
          streamStatus.value = text
        },
        onDone: () => {
          // citations/meta already set from onMeta; nothing else to do
        },
        onError: (detail) => {
          ElMessage.error(detail)
        },
      },
      controller.signal,
    )
  } catch (e: any) {
    if (e?.name === 'AbortError') {
      // User stopped generation — keep the partial content
      ElMessage.info('已停止生成')
    } else {
      // If nothing was streamed, remove the empty placeholder
      if (!streamMsg.content) {
        const idx = chatHistory.value.indexOf(streamMsg)
        if (idx >= 0) chatHistory.value.splice(idx, 1)
      }
      ElMessage.error(e?.message || '发送失败')
    }
  } finally {
    chatSending.value = false
    activeController.value = null
  }
}

function sendQuickAction(prompt: string) {
  sendMessage(prompt)
}

function scrollToBottom() {
  nextTick(() => {
    if (chatMessagesRef.value) {
      chatMessagesRef.value.scrollTop = chatMessagesRef.value.scrollHeight
    }
  })
}

function goBack() {
  if (paperDetail.value?.project_id) router.push(`/project/${paperDetail.value.project_id}`)
  else router.back()
}

// ── Notes ──
const notes = ref<Note[]>([])
const selectedText = ref('')
const noteAnchor = ref('')
const noteContent = ref('')
const noteTags = ref('')
const noteSummarize = ref(false)
const savingNote = ref(false)
const editingId = ref<number | null>(null)
const editAnchor = ref('')
const editContent = ref('')
const summarizingId = ref<number | null>(null)
const exportingNotes = ref(false)

function captureSelection() {
  const sel = window.getSelection()
  if (!sel || sel.isCollapsed) {
    selectedText.value = ''
    return
  }
  const text = sel.toString().trim()
  if (text && text.length < 2000) selectedText.value = text
}

async function loadNotes() {
  try {
    const res = await noteApi.list({ paper_id: paperId.value })
    notes.value = res.data
  } catch { /* handled by interceptor */ }
}

async function saveNote() {
  if (!noteAnchor.value.trim() && !noteContent.value.trim()) return
  savingNote.value = true
  try {
    const res = await noteApi.create({
      paper_id: paperId.value,
      anchor_text: noteAnchor.value.trim() || undefined,
      content: noteContent.value.trim() || undefined,
      tags: noteTags.value.split(/[,，]/).map(t => t.trim()).filter(Boolean),
      summarize: noteSummarize.value,
    })
    notes.value.unshift(res.data)
    noteAnchor.value = ''
    noteContent.value = ''
    noteTags.value = ''
    noteSummarize.value = false
    selectedText.value = ''
    ElMessage.success('笔记已添加')
  } catch { /* handled by interceptor */ }
  finally {
    savingNote.value = false
  }
}

function startEdit(n: Note) {
  editingId.value = n.id
  editAnchor.value = n.anchor_text || ''
  editContent.value = n.content || ''
}

async function saveEdit(n: Note) {
  savingNote.value = true
  try {
    const res = await noteApi.update(n.id, {
      anchor_text: editAnchor.value.trim() || undefined,
      content: editContent.value.trim() || undefined,
    })
    Object.assign(n, res.data)
    editingId.value = null
    ElMessage.success('已保存')
  } catch { /* handled by interceptor */ }
  finally {
    savingNote.value = false
  }
}

async function deleteNote(id: number) {
  try {
    await ElMessageBox.confirm('确定删除这条笔记吗？', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await noteApi.remove(id)
    notes.value = notes.value.filter(n => n.id !== id)
    ElMessage.success('已删除')
  } catch { /* handled by interceptor */ }
}

async function doSummarize(id: number) {
  summarizingId.value = id
  try {
    const res = await noteApi.summarize(id)
    const idx = notes.value.findIndex(n => n.id === id)
    if (idx >= 0) notes.value[idx] = res.data
    ElMessage.success('AI 提炼完成')
  } catch { /* handled by interceptor */ }
  finally {
    summarizingId.value = null
  }
}

async function exportNotes() {
  if (!paperDetail.value?.project_id) return
  exportingNotes.value = true
  try {
    await noteApi.exportMarkdown(paperDetail.value.project_id, paperId.value)
    ElMessage.success('已导出 Markdown')
  } catch { /* handled by interceptor */ }
  finally {
    exportingNotes.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.reading-page {
  height: calc(100vh - 60px);
  display: flex;
  flex-direction: column;
}

.center-state {
  padding: 40px 20px;
}

/* ── Split Layout ── */
.reading-split {
  display: flex;
  flex: 1;
  gap: 12px;
  overflow: hidden;
  height: 100%;
}

.left-panel {
  flex: 7;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

.right-panel {
  flex: 4;
  display: flex;
  flex-direction: column;
  min-width: 0;
  border-left: 1px solid #e4e7ed;
  padding-left: 12px;
}

/* ── Left Panel Header ── */
.panel-header {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.panel-header-info {
  flex: 1;
  min-width: 0;
}

.paper-title {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.paper-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #64748b;
}

.meta-item {
  white-space: nowrap;
}

/* ── View Tabs ── */
.view-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.view-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow: hidden;
}
.view-tabs :deep(.el-tab-pane) {
  height: 100%;
}

.pdf-viewer {
  height: 100%;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  overflow: hidden;
  display: flex;
}

.pdf-iframe {
  width: 100%;
  height: 100%;
  display: block;
  border: none;
}

.text-viewer {
  height: 100%;
  overflow-y: auto;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
  padding: 20px;
}

.parsed-text {
  font-family: 'Georgia', 'Times New Roman', 'Noto Serif CJK SC', serif;
  font-size: 14px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-wrap: break-word;
  margin: 0;
  color: #1e293b;
}

/* ── Right Panel Tabs ── */
.right-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.right-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow: hidden;
}
.right-tabs :deep(.el-tab-pane) {
  height: 100%;
}

/* ── Analysis Panel ── */
.analysis-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #64748b;
  margin-bottom: 12px;
}

.analysis-panel {
  height: 100%;
  overflow-y: auto;
}

.analysis-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 200px;
  color: #94a3b8;
  font-size: 14px;
}

.analysis-content {
  padding-bottom: 16px;
}

.one-sentence {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 12px;
  margin-bottom: 12px;
  background: linear-gradient(135deg, #eff6ff, #dbeafe);
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  color: #1e40af;
  line-height: 1.5;
}

.analysis-collapse {
  margin-bottom: 12px;
}

.section-content {
  font-size: 13px;
  line-height: 1.7;
  color: #334155;
  padding: 4px 0;
}

.analysis-actions {
  display: flex;
  justify-content: center;
  margin-top: 8px;
}

/* ── Chat Panel ── */
.chat-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.quick-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  flex-shrink: 0;
}
.quick-actions .el-button {
  font-size: 12px;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  margin: 8px 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chat-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 100%;
  color: #94a3b8;
  font-size: 13px;
}

.chat-msg-wrapper {
  margin-bottom: 4px;
}

.chat-msg {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.msg-footer {
  margin-top: 4px;
  margin-left: 36px;
}

.citation-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.citation-tag {
  font-size: 11px;
  cursor: pointer;
}

.citation-tag:hover {
  background: #e0e7ff;
}

.suggestion-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.suggestion-buttons .el-button {
  font-size: 12px;
}

.chat-msg.user {
  flex-direction: row-reverse;
}

.msg-avatar {
  flex-shrink: 0;
}

.msg-bubble {
  max-width: 80%;
  padding: 8px 12px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.chat-msg.user .msg-bubble {
  background: #3b82f6;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.chat-msg.assistant .msg-bubble {
  background: #f1f5f9;
  color: #1e293b;
  border-bottom-left-radius: 4px;
}

.thinking .dot-pulse {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #3b82f6;
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}

.chat-input-bar {
  flex-shrink: 0;
}

.chat-input-bar :deep(.el-input-group__append) {
  padding: 0 8px;
}

/* ── Mode Selector ── */
.chat-input-area {
  flex-shrink: 0;
}

.chat-mode-selector {
  display: flex;
  justify-content: center;
  margin-bottom: 8px;
}

.chat-mode-selector .el-radio-button__inner {
  font-size: 12px;
  padding: 4px 12px;
}

.stream-status {
  text-align: center;
  font-size: 12px;
  color: #64748b;
  margin-bottom: 6px;
  animation: status-blink 1.6s ease-in-out infinite;
}

@keyframes status-blink {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}

/* ── Notes Panel ── */
.notes-panel {
  height: 100%;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.notes-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.notes-count {
  font-size: 13px;
  color: #64748b;
}

.note-compose {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  flex-shrink: 0;
}

.note-compose-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sel-hint {
  font-size: 12px;
  color: #3b82f6;
}

.note-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.note-item {
  padding: 12px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.note-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.note-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.note-item-actions {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.note-anchor {
  font-size: 13px;
  color: #1e40af;
  background: #eff6ff;
  border-left: 3px solid #3b82f6;
  padding: 6px 8px;
  border-radius: 4px;
  margin-bottom: 6px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.note-content {
  font-size: 13px;
  color: #334155;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  margin-bottom: 6px;
}

.note-summary {
  font-size: 12px;
  color: #047857;
  background: #ecfdf5;
  border-radius: 6px;
  padding: 8px 10px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.summary-label {
  font-weight: 600;
}

.note-edit {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>
