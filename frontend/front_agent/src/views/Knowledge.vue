<script setup>
// 知识库文档管理（仅管理员）：上传文档 → 后端排队做 OCR/切分/向量化 → 本页轮询看进度
// 与其它 CRUD 页最大的不同：这里是「异步任务」视角——
//   上传返回 202（只表示"已入队"），真正的状态要靠 status/progress 轮询刷新
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Upload } from '@element-plus/icons-vue'
import {
  deleteKnowledgeDocumentApi,
  getKnowledgeChunksApi,
  getKnowledgePageListApi,
  reprocessKnowledgeDocumentApi,
  updateKnowledgeEnabledApi,
  uploadKnowledgeDocumentApi,
} from '@/api/knowledge'

// ===== 与后端 settings 对齐的上传约束（改这里必须同步改后端，否则前端放行、后端 413/415） =====
const ALLOWED_EXTENSIONS = ['.docx', '.pdf', '.xlsx', '.md', '.zip', '.jpg', '.jpeg', '.png', '.webp']
const MAX_FILE_BYTES = 20 * 1024 * 1024 // MAX_KNOWLEDGE_FILE_BYTES = 20MiB
const POLL_INTERVAL_MS = 3000 // 排队/处理中的轮询间隔；后端 worker 本身是 2 秒扫一次

// ===== 查询参数 =====
// 本页没有"新增/编辑弹窗"：文档内容就是上传的文件，所以只有上传、启停、重处理、删除四个动作
const params = ref({
  page: 1,
  pageSize: 10,
  keywords: '',
  status: null, // null = 全部状态
})

const tableData = ref([])
const total = ref(0)
const loading = ref(false)
const uploading = ref(false)

// 分块预览弹窗状态
const chunkVisible = ref(false)
const chunkLoading = ref(false)
const chunks = ref([])
const currentDoc = ref(null)

let pollTimer = null // setInterval 句柄，卸载时必须清掉

// 状态码 → 文案 / 颜色（四态，与后端 Literal 完全一致）
const statusText = (status) =>
  ({ queued: '排队中', processing: '处理中', completed: '已完成', failed: '失败' })[status] ?? status
const statusType = (status) =>
  (
    { queued: 'info', processing: 'warning', completed: 'success', failed: 'danger' }[status] ??
    'info'
  )

// 还有活的文档吗——决定要不要继续轮询
function hasActiveDoc() {
  return tableData.value.some((row) => row.status === 'queued' || row.status === 'processing')
}

// 字节数转可读单位：只在表格这一处用，所以写在本页，不抽公共工具文件
function formatSize(bytes) {
  if (!bytes && bytes !== 0) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

// 后端 created_at 是 UTC 带 Z 的 ISO 串（2026-10-19T21:11:57.082567Z），直显会出现 T/Z/微秒且比本地早 8 小时
// new Date 会按 Z 识别为 UTC，再用 getHours 等方法取本地时区 → 显示的就是浏览器所在时区
function formatTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value // 解析失败宁可显示原值，不显示 NaN
  const pad = (num) => String(num).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours()
  )}:${pad(date.getMinutes())}`
}

// silent=true 用于轮询：不闪 loading 遮罩，避免每 3 秒表格"糊一下"
async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    const res = await getKnowledgePageListApi({
      page: params.value.page,
      // 字段翻译点：camelCase → 查询串 snake_case
      page_size: params.value.pageSize,
      keywords: params.value.keywords,
      status: params.value.status, // null/undefined 时 axios 不拼该参数 = 不筛状态
    })
    if (res.code >= 200 && res.code < 300) {
      tableData.value = res.data?.list ?? []
      total.value = res.data?.total ?? 0
    }
  } catch {
    // 网络/HTTP 层失败的提示已由 request.js 拦截器统一弹出，这里只终结异常链
  } finally {
    if (!silent) loading.value = false
  }
}

function handleSearch() {
  params.value.page = 1
  load()
}

// ===== 上传 =====
// 前端先按后端同一套规则挡一遍：省一次必败的往返，但后端仍是唯一权威（它会回 413/415）
function beforeUpload(file) {
  const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    ElMessage.error(`只支持 ${ALLOWED_EXTENSIONS.join(' / ')} 格式`)
    return false
  }
  if (file.size > MAX_FILE_BYTES) {
    ElMessage.error(`文档大小不能超过 ${formatSize(MAX_FILE_BYTES)}`)
    return false
  }
  return true
}

// 自定义上传：:http-request 接管默认 XHR，回调收到 { file }
async function handleUpload({ file }) {
  uploading.value = true
  try {
    const res = await uploadKnowledgeDocumentApi(file)
    // 后端返回 HTTP 201/202 段，2xx 判定正好覆盖
    if (res.code >= 200 && res.code < 300) {
      ElMessage.success(res.message || '文档已上传，正在排队处理！')
      handleSearch() // 回到第一页：新文档按 id 倒序在最前，且要立刻看到它的 queued 状态
    }
  } catch {
    // 413/415 等业务失败的提示已由拦截器弹出，这里只终结异常链
  } finally {
    uploading.value = false
  }
}

// ===== 单个文档的四个动作 =====
// 重新处理：失败或想换模型重跑时用；同样是 202 排队，所以成功后要刷新让轮询接管
async function handleReprocess(row) {
  const ok = await ElMessageBox.confirm(
    `确认重新处理 [${row.original_name}]？会重新走一遍解析与向量化。`,
    '重新处理',
    { type: 'warning' },
  ).catch(() => false)
  if (!ok) return
  try {
    const res = await reprocessKnowledgeDocumentApi(row.id)
    if (res.code >= 200 && res.code < 300) {
      ElMessage.success(res.message || '已重新加入处理队列！')
      load()
    }
  } catch {
    // 提示归拦截器
  }
}

// 启停：用 :model-value + @change，不让 el-switch 直接改行数据——
// 服务端才是真相；请求失败时 load() 把开关弹回原位，避免出现"界面显示已启用、后端没改"
async function handleToggleEnabled(row, enabled) {
  try {
    const res = await updateKnowledgeEnabledApi(row.id, enabled)
    if (res.code >= 200 && res.code < 300) {
      ElMessage.success(res.message || (enabled ? '已启用！' : '已停用！'))
      row.enabled = enabled // 成功才把本地这一行对齐，省一次整表刷新
    } else {
      load()
    }
  } catch {
    load() // 失败：重拉列表，开关回弹到后端真实值
  }
}

async function handleDelete(row) {
  const ok = await ElMessageBox.confirm(
    `确认删除 [${row.original_name}]？其切块与向量一并清除。`,
    '确认删除',
    { type: 'warning' },
  ).catch(() => false)
  if (!ok) return
  try {
    const res = await deleteKnowledgeDocumentApi(row.id)
    if (res.code >= 200 && res.code < 300) {
      // 删掉本页最后一条时回退一页，避免停在越界空页
      if (tableData.value.length === 1 && params.value.page > 1) {
        params.value.page -= 1
      }
      ElMessage.success(res.message || '删除成功！')
      load()
    }
  } catch {
    // 提示归拦截器
  }
}

// 分块预览：点开才拉（列表接口不返回 content，向量也不下发）
async function handleViewChunks(row) {
  currentDoc.value = row
  chunks.value = []
  chunkVisible.value = true
  chunkLoading.value = true
  try {
    const res = await getKnowledgeChunksApi(row.id)
    if (res.code >= 200 && res.code < 300) {
      chunks.value = res.data ?? []
    }
  } catch {
    // 提示归拦截器
  } finally {
    chunkLoading.value = false
  }
}

// 挂载：拉一次列表，并起一个定时器——只在"有排队/处理中的文档"时才真的发请求
onMounted(() => {
  load()
  pollTimer = setInterval(() => {
    if (hasActiveDoc()) load(true)
  }, POLL_INTERVAL_MS)
})

// 卸载：定时器必须清，否则离开本页后还在后台打接口
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
})
</script>

<template>
  <!-- 玻璃卡：与 manager 子页面族同款外壳 -->
  <div class="know-card">
    <h3 class="know-title">知识库管理</h3>

    <!-- 工具栏：关键词 + 状态筛选 + 查询 + 上传 -->
    <div class="know-toolbar">
      <el-input
        v-model="params.keywords"
        placeholder="搜索文件名"
        clearable
        class="know-toolbar__input"
        @keyup.enter="handleSearch"
        @clear="handleSearch"
      />
      <el-select
        v-model="params.status"
        placeholder="全部状态"
        clearable
        class="know-toolbar__select"
        @change="handleSearch"
      >
        <el-option value="queued" label="排队中" />
        <el-option value="processing" label="处理中" />
        <el-option value="completed" label="已完成" />
        <el-option value="failed" label="失败" />
      </el-select>
      <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
      <!-- 上传：accept 只是让选择框默认过滤，真正的类型闸门在 beforeUpload + 后端 415 -->
      <el-upload
        :http-request="handleUpload"
        :show-file-list="false"
        :before-upload="beforeUpload"
        :accept="ALLOWED_EXTENSIONS.join(',')"
      >
        <el-button type="success" :icon="Upload" :loading="uploading">上传文档</el-button>
      </el-upload>
      <span class="know-toolbar__hint">
        支持 {{ ALLOWED_EXTENSIONS.join(' / ') }}，单个不超过 {{ formatSize(MAX_FILE_BYTES) }}
      </span>
    </div>

    <el-table v-loading="loading" :data="tableData" style="width: 100%">
      <!-- 文档：文件名独占一列（两行截断 + 原生 title），类型/大小压成下方小字 -->
      <el-table-column label="文档" min-width="300">
        <template #default="{ row }">
          <div class="know-doc">
            <span class="know-doc__name" :title="row.original_name">{{ row.original_name }}</span>
            <span class="know-doc__meta">{{ row.extension }} · {{ formatSize(row.size) }}</span>
          </div>
        </template>
      </el-table-column>

      <!-- 状态：tag + 按需出现的进度/失败原因，不再各占一整列 -->
      <el-table-column label="状态" width="200">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag>
          <!-- 后端 progress 是 0-100 的整数；百分比只在"还没跑完"时有信息量 -->
          <el-progress
            v-if="row.status === 'queued' || row.status === 'processing'"
            class="know-status__progress"
            :percentage="Number(row.progress) || 0"
            :stroke-width="6"
          />
          <!-- 失败原因以前固定占一列，正常数据全是"-"；现在只在真失败时内联出现 -->
          <div
            v-if="row.status === 'failed' && row.error_message"
            class="know-error"
            :title="row.error_message"
          >
            {{ row.error_message }}
          </div>
        </template>
      </el-table-column>

      <el-table-column prop="chunk_count" label="分块数" width="80" />
      <el-table-column label="启用" width="70">
        <!-- :model-value + @change：不让开关直接改行数据，服务端才是真相 -->
        <template #default="{ row }">
          <el-switch
            :model-value="row.enabled"
            :disabled="row.status !== 'completed'"
            @change="(val) => handleToggleEnabled(row, val)"
          />
        </template>
      </el-table-column>
      <el-table-column label="上传时间" width="160">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <!-- 操作列 240px + nowrap：实测三个按钮占 210px + 左右内边距 24px，230 会把"删除"挤成省略号 -->
      <el-table-column label="操作" width="240" class-name="know-actions">
        <template #default="{ row }">
          <el-button size="small" text bg @click="handleViewChunks(row)">预览分块</el-button>
          <el-button size="small" text bg @click="handleReprocess(row)">重新处理</el-button>
          <el-button size="small" text bg type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!loading && !tableData.length" description="还没有上传任何知识文档" />

    <div class="know-pager">
      <el-pagination
        v-model:current-page="params.page"
        v-model:page-size="params.pageSize"
        :total="total"
        :page-sizes="[10, 20, 50]"
        background
        layout="total, sizes, prev, pager, next"
        @current-change="load()"
        @size-change="handleSearch"
      />
    </div>
  </div>

  <!-- 分块预览抽屉：append-to-body 躲开祖先 backdrop-filter 对 fixed 的劫持（本项目已踩过） -->
  <el-dialog
    v-model="chunkVisible"
    :title="`分块预览 · ${currentDoc?.original_name ?? ''}`"
    width="720px"
    append-to-body
  >
    <div v-loading="chunkLoading" class="know-chunks">
      <!-- 后端只下发预览字段，完整向量不出网关；这里也不尝试渲染图片（storage_key 是私有目录） -->
      <div v-for="chunk in chunks" :key="chunk.id" class="know-chunk">
        <div class="know-chunk__head">
          <el-tag size="small" type="info">#{{ chunk.chunk_index }}</el-tag>
          <el-tag size="small">{{ chunk.modality }}</el-tag>
          <span v-if="chunk.page_number" class="know-chunk__meta">第 {{ chunk.page_number }} 页</span>
          <span v-if="chunk.sheet_name" class="know-chunk__meta">
            工作表 {{ chunk.sheet_name }}
          </span>
          <span v-if="chunk.heading_path" class="know-chunk__meta">
            {{ chunk.heading_path }}
          </span>
        </div>
        <div class="know-chunk__body">{{ chunk.content }}</div>
      </div>
      <el-empty v-if="!chunkLoading && !chunks.length" description="这份文档还没有切块结果" />
    </div>
    <template #footer>
      <el-button @click="chunkVisible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
/* 外壳：manager 子页面族同款玻璃卡 */
.know-card {
  padding: 24px;
  background-color: var(--color-surface-glass);
  backdrop-filter: blur(12px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}

.know-title {
  margin: 0 0 16px;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.know-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.know-toolbar__input {
  width: 200px;
}

.know-toolbar__select {
  width: 140px;
}

/* 上传约束提示：弱化色，避免和按钮抢视觉 */
.know-toolbar__hint {
  font-size: 12px;
  color: var(--color-text-muted);
}

/* 表格透明化：与另几页同款 */
.know-card :deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(245, 247, 250, 0.7);
}

/* 文档列：文件名两行截断（和 Lab 简介同款：截断交给 CSS，全文交给原生 title） */
.know-doc {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.know-doc__name {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  word-break: break-all;
  color: var(--color-text-primary);
}

/* 类型 · 大小：次要信息，压成一行弱化小字 */
.know-doc__meta {
  font-size: 12px;
  color: var(--color-text-muted);
}

/* 进度条跟在状态标签下面：cell 默认行高会把它顶得太远，所以自己定间距 */
.know-status__progress {
  margin-top: 6px;
}

.know-error {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.4;
  word-break: break-all;
  color: var(--el-color-danger, #f56c6c);
}

/* 操作列禁止换行：与 Lab/Equipment 同款双保险 */
.know-card :deep(.know-actions .cell) {
  white-space: nowrap;
}

/* 分块预览区：限高滚动，长文档也不会把弹窗撑到屏幕外 */
.know-chunks {
  max-height: 60vh;
  overflow-y: auto;
}

.know-chunk {
  padding: 10px 12px;
  margin-bottom: 10px;
  background-color: var(--color-page-bg);
  border: 1px solid var(--color-border);
  border-radius: 8px;
}

.know-chunk__head {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
}

.know-chunk__meta {
  font-size: 12px;
  color: var(--color-text-muted);
}

/* 切块正文：保留模型/文档里的原始换行与空格 */
.know-chunk__body {
  font-size: 13px;
  line-height: 1.7;
  color: var(--color-text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.know-pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
