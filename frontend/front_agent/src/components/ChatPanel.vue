<script setup>
// AI 对话面板（纯 UI）：消息列表 + 输入框，状态全部来自 utils/aiChat.js 的共享 ref
// 两个消费方：① views/AIChat.vue（整页版）② layout/Layout.vue 的右下角气泡抽屉
// 之所以只抽 UI 不抽状态：状态若留在组件里，两个实例就是两条独立对话，等于没解决问题
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
// 共享的对话状态与动作：messages / loading / send / clear 都是全站同一份
import { useAiChat } from '@/utils/aiChat'
// 模型输出的是 Markdown（表格/列表/代码块都可能出现），这里只做"解析 + 消毒"两步：
// marked 负责语法 → HTML（它不做任何安全过滤），DOMPurify 负责把 <script>、onerror 这类剔掉，
// 消毒后的字符串才允许进 v-html。用户消息不走这条路，仍是纯文本插值。
import { renderMarkdown } from '@/utils/markdown'

const {
  messages,
  loading,
  sessionId,
  sessions,
  models,
  activeModel,
  lastUsage,
  contextWindow,
  supportsVision,
  send,
  loadModels,
  loadSessions,
  openSession,
  newSession,
  removeSession,
  renameSession,
  confirmPendingAction,
  cancelPendingAction,
} = useAiChat()

// 工具名 → 人话。后端 used_tools 给的是函数名，直接显示用户读不懂
const TOOL_LABELS = {
  list_open_labs: '开放实验室列表',
  list_lab_equipments: '实验室设备',
  prepare_reservation: '预约信息整理',
}

// 草稿状态 → 卡片标题/兜底文案（resultMessage 优先，因为那是后端原话）
const ACTION_STATUS_TEXT = {
  pending: '待确认预约',
  completed: '已确认预约',
  cancelled: '已取消的草稿',
  expired: '已过期的草稿',
}

// 后端 time 序列化成 "09:00:00"，卡片只要时分
const hhmm = (value) => (value ? String(value).slice(0, 5) : '-')

// 文本依据按文件名去重：同一份文档可能命中多个 chunk，列两遍没有意义。
// 带图片的来源走下面的图片区，不重复出现在文字清单里。
function textSources(item) {
  const seen = new Set()
  return (item.sources ?? []).filter((source) => {
    if (source.imageObjectUrl) return false
    if (seen.has(source.file_name)) return false
    seen.add(source.file_name)
    return true
  })
}

// expires_at 是 UTC 带 Z 的 ISO；直接截字符串会比本地早 8 小时，必须走 Date 转换
function deadlineText(iso) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '-'
  const pad = (num) => String(num).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(
    date.getMinutes()
  )}`
}

// 过期判断只看本地时间：DB 里可能还写着 pending，但确认必然 409，所以不给他按钮
function actionExpired(action) {
  const deadline = new Date(action?.expires_at).getTime()
  return Number.isNaN(deadline) ? false : deadline <= Date.now()
}

// 实时响应的 PendingReservationAction 不带 status（只有历史恢复用的 SessionPendingAction 有），
// 缺省就是"刚建好的待确认"。判断放在显示层做归一，不管数据从哪条路来都不会漏。
const actionStatus = (action) => action?.status ?? 'pending'

// 卡片是否还能操作：状态是 pending 且没到截止时间
function actionActionable(action) {
  return actionStatus(action) === 'pending' && !actionExpired(action)
}

// 流式过程中，正在生成的那条助手消息自己带 status（"正在查询开放实验室…"）。
// 这时底部再挂一条"正在思考…"占位就成了两个指示器叠着晃眼，所以让位给它。
const hasLiveStatus = computed(() => messages.value.some((item) => item.status))

// token 数加千分位；窗口大小用 K/M 简写，进度条旁边一眼能读
const tokenText = (value) => Number(value ?? 0).toLocaleString()
const windowText = (size) =>
  size >= 1_000_000 ? `${size / 1_000_000}M` : `${Math.round(size / 1000)}K`
// 上下文占用百分比：后端 usage.input_tokens 已经包含整段历史，所以只看最近一轮，不做各轮累加
const contextPercent = computed(() => {
  if (!contextWindow.value || !lastUsage.value) return 0
  return Math.min(100, Math.round((lastUsage.value.input_tokens / contextWindow.value) * 100))
})
// 1M 的窗口下进度条几乎永远贴着 0，所以把百分比也写进文字，不然只有条看不出变化
const contextRatioText = computed(() => {
  if (!contextWindow.value || !lastUsage.value) return ''
  const ratio = lastUsage.value.input_tokens / contextWindow.value
  return ratio < 0.01 ? `${(ratio * 100).toFixed(1)}%` : `${Math.round(ratio * 100)}%`
})

// 删除当前会话（会话内容也一起删）；没有 session_id 说明这轮还没落库，按钮本身就是禁用态
async function handleRemoveSession() {
  if (!sessionId.value) return
  const ok = await ElMessageBox.confirm('确认删除当前会话？其中的消息会一并删除。', '删除会话', {
    type: 'warning',
  }).catch(() => false)
  if (!ok) return
  await removeSession(sessionId.value)
}

// 改当前会话的标题：后端默认只截首条提问前30字，问一句"你好"就永久叫"你好"
async function handleRename() {
  if (!sessionId.value) return
  const current = sessions.value.find((item) => item.id === sessionId.value)
  const result = await ElMessageBox.prompt('标题只用于在会话列表里认出这段对话', '重命名会话', {
    inputValue: current?.title ?? '',
    inputPlaceholder: '输入新标题（100 字以内）',
    // 空标题后端会 422，这里先挡一道，省一次必败的请求
    inputValidator: (value) => (value && value.trim() ? true : '标题不能为空'),
    confirmButtonText: '保存',
    cancelButtonText: '取消',
  }).catch(() => null)
  if (!result) return
  const ok = await renameSession(sessionId.value, result.value.trim())
  if (ok) ElMessage.success('会话标题已更新！')
}

// 挂载时拉一次模型白名单和会话列表；两个入口各自挂载会各拉一次，都是幂等 GET
onMounted(() => {
  loadModels()
  loadSessions()
})

// 自愈：挂载时如果这两个请求赶上前端重启之类的失败，下拉框会一直是空的灰框，
// 所以展开时再补拉一次——不弹提示、不挡操作，点开了就有数据
function reloadIfEmpty(visible) {
  if (!visible) return
  if (!models.value.length) loadModels()
  if (!sessions.value.length) loadSessions()
}

// 输入框内容属于"局部 UI 状态"，不该进全局 store——两个入口不会同时输入
const input = ref('')
const listRef = ref(null)
const fileInputRef = ref(null)
const selectedImage = ref(null)
const selectedPreviewUrl = ref(null)

const ALLOWED_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp'])
const MAX_IMAGE_BYTES = 10 * 1024 * 1024

function revokeSelectedPreview() {
  if (selectedPreviewUrl.value) URL.revokeObjectURL(selectedPreviewUrl.value)
  selectedPreviewUrl.value = null
}

function chooseImage() {
  // 当前模型不支持图片时不弹文件框（按钮本身也已禁用，这里再挡一层键盘触发）
  if (!loading.value && supportsVision.value) fileInputRef.value?.click()
}

function handleImageChange(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  if (!ALLOWED_IMAGE_TYPES.has(file.type)) {
    ElMessage.warning('只支持 JPG、PNG 或 WebP 图片')
    return
  }
  if (file.size > MAX_IMAGE_BYTES) {
    ElMessage.warning('查询图片不能超过 10 MiB')
    return
  }
  revokeSelectedPreview()
  selectedImage.value = file
  selectedPreviewUrl.value = URL.createObjectURL(file)
}

function removeSelectedImage() {
  selectedImage.value = null
  revokeSelectedPreview()
}

onBeforeUnmount(revokeSelectedPreview)

// 滚到底部：push 之后 DOM 还没更新，直接读 scrollHeight 是旧值，必须等 nextTick
function scrollToBottom() {
  nextTick(() => {
    const el = listRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

// 监听"消息条数 + 是否发送中 + 最后一条的正文长度"：
// 前两个是原来的需求；第三个是流式必需的 —— token 只往已有消息上追加，
// 条数不变，不监听长度的话正文会往下长、视口却停在原地。
watch(
  () => [
    messages.value.length,
    loading.value,
    messages.value[messages.value.length - 1]?.content?.length ?? 0,
  ],
  () => scrollToBottom(),
  { immediate: true },
)

// 发送：交给共享状态处理入队与请求；这里只负责清空输入框
// 失败也清空——用户的原话已经在气泡里留着了，重问一次比让他重新打字友好
async function handleSend() {
  const text = input.value
  if ((!text.trim() && !selectedImage.value) || loading.value) return
  const imageFile = selectedImage.value
  input.value = ''
  removeSelectedImage()
  await send(text, imageFile)
}
</script>

<template>
  <div class="chat-panel">
    <!-- ===== 会话行：下拉即"会话列表"，标题由后端取首条提问前 30 字 ===== -->
    <div class="chat-panel__bar">
      <!-- :model-value + @change：切会话要等后端拉完历史才算成功，失败时下拉回弹到原值 -->
      <el-select
        class="chat-panel__session"
        :model-value="sessionId"
        placeholder="新对话（未保存）"
        :disabled="loading"
        @visible-change="reloadIfEmpty"
        @change="(id) => openSession(id)"
      >
        <el-option v-for="item in sessions" :key="item.id" :value="item.id" :label="item.title" />
      </el-select>
      <el-button size="small" :disabled="loading" @click="newSession">新对话</el-button>
      <!-- 改名与删除都只对"已经落库的会话"有意义，所以同一条件一起出现 -->
      <el-button v-if="sessionId" size="small" :disabled="loading" @click="handleRename">
        重命名
      </el-button>
      <el-button
        v-if="sessionId"
        size="small"
        text
        type="danger"
        :disabled="loading"
        @click="handleRemoveSession"
      >
        删除
      </el-button>
    </div>

    <!-- ===== 状态行：用哪个模型、思考层级多高都由管理员在「AI模型配置」页设，
                 普通用户这里只显示、不调节 ===== -->
    <div class="chat-panel__bar">
      <span class="chat-panel__model-info">
        当前模型：{{ activeModel || '后端默认（提问后显示）' }}
      </span>
      <!-- 上下文进度：分母是当前模型的 context_window，分子是最近一轮的 input_tokens -->
      <div v-if="contextWindow && lastUsage" class="chat-panel__context">
        <el-progress :percentage="contextPercent" :stroke-width="6" :show-text="false" />
        <span class="chat-panel__context-text">
          已用 {{ tokenText(lastUsage.input_tokens) }} / {{ windowText(contextWindow) }} ·
          {{ contextRatioText }}
        </span>
      </div>
    </div>

    <!-- 消息区：flex:1 撑满父容器剩余高度，滚动只发生在这一层 -->
    <div ref="listRef" class="chat-panel__log">
      <!-- 用户消息 = 纯文本插值（Vue 自动转义，写 <script> 也只当字面量显示）；
           助手消息 = Markdown 渲染，内容已过 DOMPurify，见 utils/markdown.js -->
      <div
        v-for="item in messages"
        :key="item.id"
        class="chat-panel__row"
        :class="{ 'chat-panel__row--me': item.role === 'user' }"
      >
        <div class="chat-panel__bubble" :class="{ 'chat-panel__bubble--error': item.error }">
          <el-image
            v-if="item.imageObjectUrl"
            class="chat-panel__image"
            :src="item.imageObjectUrl"
            :preview-src-list="[item.imageObjectUrl]"
            fit="contain"
          />
          <!-- 过程可见：当前状态一行 + 这一轮做过的事。steps 只用于展示，不会进历史 -->
          <div v-if="item.status" class="chat-panel__status">{{ item.status }}</div>
          <div v-if="item.steps?.length" class="chat-panel__steps">
            <div v-for="(step, index) in item.steps" :key="index">· {{ step }}</div>
          </div>
          <template v-if="item.role === 'user'">{{ item.content }}</template>
          <!-- 从历史恢复的草稿卡片没有正文（参数已经在卡片里了，再重复一遍反而容易看错），
               所以正文为空时整块不渲染 -->
          <div v-else-if="item.content" class="markdown-body" v-html="renderMarkdown(item.content)"></div>

          <!-- ===== 预约确认卡片：模型只准备草稿，点「确认预约」才真正写库 ===== -->
          <div v-if="item.pendingAction" class="chat-panel__action">
            <div class="chat-panel__action-head">
              <span class="chat-panel__action-title">
                {{
                  actionActionable(item.pendingAction)
                    ? ACTION_STATUS_TEXT.pending
                    : (ACTION_STATUS_TEXT[actionStatus(item.pendingAction)] ?? '预约草稿')
                }}
              </span>
              <el-tag
                size="small"
                :type="actionActionable(item.pendingAction) ? 'warning' : 'info'"
              >
                {{
                  actionActionable(item.pendingAction)
                    ? '等待确认'
                    : actionStatus(item.pendingAction) === 'completed'
                      ? '已完成'
                      : '不可再操作'
                }}
              </el-tag>
            </div>

            <dl class="chat-panel__action-body">
              <div>
                <dt>实验室</dt>
                <dd>{{ item.pendingAction.lab_name || `#${item.pendingAction.lab_id}` }}</dd>
              </div>
              <div v-if="item.pendingAction.equipment_name">
                <dt>设备</dt>
                <dd>{{ item.pendingAction.equipment_name }}</dd>
              </div>
              <div>
                <dt>时间</dt>
                <dd>
                  {{ item.pendingAction.date }}
                  {{ hhmm(item.pendingAction.start_time) }}–{{ hhmm(item.pendingAction.end_time) }}
                </dd>
              </div>
              <div v-if="item.pendingAction.remark">
                <dt>备注</dt>
                <dd>{{ item.pendingAction.remark }}</dd>
              </div>
            </dl>

            <!-- 还能操作：给两个按钮 + 截止时间 -->
            <template v-if="actionActionable(item.pendingAction)">
              <div class="chat-panel__action-tip">
                {{ deadlineText(item.pendingAction.expires_at) }} 前有效；确认后才会真正提交预约
              </div>
              <div class="chat-panel__action-btns">
                <el-button
                  type="primary"
                  size="small"
                  :loading="item.pendingAction.submitting"
                  @click="confirmPendingAction(item)"
                >
                  确认预约
                </el-button>
                <el-button
                  size="small"
                  :disabled="item.pendingAction.submitting"
                  @click="cancelPendingAction(item)"
                >
                  取消草稿
                </el-button>
              </div>
            </template>
            <!-- 不能操作：只显示结果状态，后端原文优先 -->
            <div v-else class="chat-panel__action-done">
              {{
                item.pendingAction.resultMessage ||
                (actionStatus(item.pendingAction) === 'pending'
                  ? '已超过确认时间，请重新发起预约'
                  : '这张卡片已经不能操作了')
              }}
              <span v-if="item.pendingAction.reservation_id">
                （预约编号 {{ item.pendingAction.reservation_id }}）
              </span>
            </div>
          </div>

          <!-- 文字依据：正文不再写“依据：《…》”，改由这里统一展示，避免回答变长 -->
          <div v-if="textSources(item).length" class="chat-panel__refs">
            <div class="chat-panel__refs-title">依据</div>
            <ul>
              <li v-for="source in textSources(item)" :key="source.chunk_id">
                {{ source.file_name }}
                <template v-if="source.page_number"> · 第{{ source.page_number }}页</template>
              </li>
            </ul>
          </div>

          <div v-if="item.sources?.some((source) => source.imageObjectUrl)" class="chat-panel__sources">
            <div class="chat-panel__sources-title">相关知识库图片</div>
            <div class="chat-panel__source-grid">
              <figure
                v-for="source in item.sources.filter((entry) => entry.imageObjectUrl)"
                :key="source.chunk_id"
                class="chat-panel__source"
              >
                <el-image
                  class="chat-panel__image"
                  :src="source.imageObjectUrl"
                  :preview-src-list="[source.imageObjectUrl]"
                  fit="contain"
                />
                <figcaption>{{ source.file_name }}<template v-if="source.page_number"> · 第{{ source.page_number }}页</template></figcaption>
              </figure>
            </div>
          </div>
          <!-- 本轮用量 + 耗时 + 实际调过的工具。usage 可能为 null（兼容层没返回），此时只显示工具 -->
          <div
            v-if="item.usage || item.usedTools?.length || item.durationMs"
            class="chat-panel__usage"
          >
            <template v-if="item.usage">
              输入 {{ tokenText(item.usage.input_tokens) }} · 输出
              {{ tokenText(item.usage.output_tokens) }} · 合计
              {{ tokenText(item.usage.total_tokens) }}
              <template v-if="item.model"> · {{ item.model }}</template>
            </template>
            <!-- 用户最关心“这一问花了多久”，放在用量前面更显眼 -->
            <template v-if="item.durationMs">
              <span v-if="item.usage"> · </span>用时 {{ (item.durationMs / 1000).toFixed(1) }} 秒
            </template>
            <!-- 让"回答里的实时数据不是编的"变成可见信息 -->
            <div v-if="item.usedTools?.length" class="chat-panel__tools">
              本回答查询了：{{ item.usedTools.map((name) => TOOL_LABELS[name] ?? name).join('、') }}
            </div>
          </div>
        </div>
      </div>

      <!-- "正在思考"占位：模型响应常要十几秒，没有它用户会以为点了没反应 -->
      <div v-if="loading && !hasLiveStatus" class="chat-panel__row">
        <div class="chat-panel__bubble chat-panel__bubble--typing">正在思考…</div>
      </div>
    </div>

    <!-- 输入区：Enter 发送、Shift + Enter 换行 -->
    <div class="chat-panel__input">
      <input
        ref="fileInputRef"
        class="chat-panel__file-input"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        @change="handleImageChange"
      />
      <div v-if="selectedPreviewUrl" class="chat-panel__selected-image">
        <img :src="selectedPreviewUrl" alt="待发送图片预览" />
        <button type="button" aria-label="移除图片" @click="removeSelectedImage">×</button>
      </div>
      <el-button :disabled="loading || !supportsVision" @click="chooseImage">选择图片</el-button>
      <el-input
        v-model="input"
        type="textarea"
        :rows="2"
        :maxlength="4000"
        show-word-limit
        :disabled="loading"
        resize="none"
        placeholder="问问实验室怎么预约、开放时间…（Enter 发送，Shift + Enter 换行）"
        @keydown.enter.exact.prevent="handleSend"
        @keydown.enter.shift.stop
      />
      <el-button type="primary" :loading="loading" @click="handleSend">发送</el-button>
    </div>
  </div>
</template>

<style scoped>
/* 面板本身是纵向 flex：消息区吃掉剩余高度，输入区固定在底部 */
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0; /* flex 子项要能收缩，否则内容多了会把父容器撑破 */
}

/* 工具条：会话一行、模型一行；窄抽屉里靠 flex-wrap 换行，不换出横向滚动条 */
.chat-panel__bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.chat-panel__session {
  flex: 1 1 160px;
  min-width: 150px;
}

/* 当前模型：只读信息，弱化到不抢内容 */
.chat-panel__model-info {
  font-size: 12px;
  color: var(--color-text-muted);
}

/* 上下文进度：条 + 文字并排，文字不换行避免"已用 1,875 /"断行 */
.chat-panel__context {
  display: flex;
  flex: 1 1 150px;
  gap: 8px;
  align-items: center;
  min-width: 150px;
}

.chat-panel__context :deep(.el-progress) {
  flex: 1;
  min-width: 60px;
}

.chat-panel__context-text {
  font-size: 12px;
  color: var(--color-text-muted);
  white-space: nowrap;
}

/* 过程状态与流水：弱化到副信息级别，别抢正文 */
.chat-panel__status {
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--color-text-muted);
}

.chat-panel__steps {
  margin-bottom: 8px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

/* 预约确认卡片：描边 + 左侧色条，跟正文区分开，让人一眼知道"这里要我决定" */
.chat-panel__action {
  padding: 12px 14px;
  margin-top: 12px;
  background-color: #fbfcff;
  border: 1px solid rgba(79, 110, 247, 0.16);
  border-left: 3px solid var(--color-accent, #4f6ef7);
  border-radius: 12px;
}

.chat-panel__action-head {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.chat-panel__action-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
}

/* 参数用 dt/dd 成对展示；窄抽屉里两列自动折成一列 */
.chat-panel__action-body {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 6px 12px;
  margin: 0;
}

.chat-panel__action-body dt {
  font-size: 12px;
  color: var(--color-text-muted);
}

.chat-panel__action-body dd {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-primary);
  word-break: break-word;
}

.chat-panel__action-tip {
  margin-top: 8px;
  font-size: 12px;
  color: var(--color-text-muted);
}

.chat-panel__action-btns {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.chat-panel__action-done {
  margin-top: 8px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.chat-panel__tools {
  margin-top: 2px;
  color: var(--color-accent, #409eff);
}

/* 每条回答底部的用量小字：与气泡正文拉开一点距离，弱化到不抢内容 */
.chat-panel__usage {
  padding-top: 6px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--color-text-muted);
  border-top: 1px dashed var(--color-border);
}

.chat-panel__log {
  flex: 1;
  min-height: 0;
  padding: 16px;
  overflow-y: auto;
  background:
    radial-gradient(600px 260px at 100% 0%, rgba(139, 92, 246, 0.06), transparent 70%),
    #f7f9fd;
  border: 1px solid var(--color-border);
  border-radius: 14px;
}

.chat-panel__row {
  display: flex;
  margin-bottom: 12px;
}

/* 我发的靠右，AI 的靠左——一个类切换，省掉教程那种 :style 对象拼接 */
.chat-panel__row--me {
  justify-content: flex-end;
}

.chat-panel__bubble {
  max-width: 85%;
  padding: 12px 16px;
  font-size: 14px;
  line-height: 1.7;
  color: var(--color-text-primary);
  word-break: break-word;
  background-color: #fff;
  border: 1px solid #edf1f8;
  border-radius: 4px 14px 14px 14px;
  box-shadow: 0 8px 20px -18px rgba(23, 35, 61, 0.3);
}

/* pre-wrap 只给用户气泡：它是纯文本，换行得靠 CSS 保留。
   助手气泡走 Markdown，marked 的 breaks:true 已经把 \n 变成 <br>，
   再叠一层 pre-wrap 会把源码里的缩进和换行也算进去，出现双倍空行 */
.chat-panel__row--me .chat-panel__bubble {
  white-space: pre-wrap;
  color: #fff;
  background: var(--gradient-accent);
  border: none;
  border-radius: 14px 4px 14px 14px;
  box-shadow: 0 10px 22px -14px rgba(79, 110, 247, 0.55);
}

.chat-panel__bubble--typing {
  font-style: italic;
  color: var(--color-text-muted);
  background-color: #fff;
  border-radius: 14px;
}

.chat-panel__bubble--error {
  color: var(--el-color-danger, #f56c6c);
  background-color: rgba(245, 108, 108, 0.08);
}

.chat-panel__input {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  margin-top: 12px;
}

.chat-panel__file-input {
  display: none;
}

.chat-panel__selected-image {
  position: relative;
  flex: 0 0 64px;
  height: 64px;
}

.chat-panel__selected-image img {
  width: 64px;
  height: 64px;
  object-fit: cover;
  border-radius: 8px;
}

.chat-panel__selected-image button {
  position: absolute;
  top: -7px;
  right: -7px;
  width: 20px;
  height: 20px;
  padding: 0;
  color: #fff;
  cursor: pointer;
  background: #f56c6c;
  border: 0;
  border-radius: 50%;
}

.chat-panel__image {
  display: block;
  width: min(100%, 420px);
  max-height: 300px;
  margin-bottom: 8px;
  border-radius: 8px;
}

.chat-panel__sources {
  padding-top: 10px;
  margin-top: 10px;
  border-top: 1px solid var(--color-border);
}

/* 文字依据：比图片区更轻，一行一份资料 */
.chat-panel__refs {
  padding-top: 8px;
  margin-top: 10px;
  border-top: 1px dashed var(--color-border);
}

.chat-panel__refs-title {
  margin-bottom: 4px;
  font-size: 12px;
  color: var(--color-text-muted);
}

.chat-panel__refs ul {
  padding: 0;
  margin: 0;
  list-style: none;
}

.chat-panel__refs li {
  font-size: 12px;
  line-height: 1.7;
  color: var(--color-text-muted);
}

.chat-panel__sources-title {
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--color-text-muted);
}

.chat-panel__source-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}

.chat-panel__source {
  margin: 0;
}

.chat-panel__source figcaption {
  font-size: 12px;
  color: var(--color-text-muted);
}

.chat-panel__input :deep(.el-textarea) {
  flex: 1;
}

/* ===== Markdown 渲染出来的节点 ===== */
/* v-html 插进来的 DOM 不会被 Vue 编译，拿不到 scoped 的 data-v 属性，
   所以这些规则全部要 :deep() 才穿得进去——这是"用了 v-html 就要放弃 scoped 直达"的代价 */

.markdown-body :deep(p) {
  margin: 0 0 6px;
}

/* 最后一个块级元素不留下边距，否则气泡底部凭空多一截空白 */
.markdown-body :deep(> :last-child) {
  margin-bottom: 0;
}

/* 模型常在回答里用 ### 小标题；气泡字号只有 14px，标题压到 15px 就够，不要它撑破版面 */
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  margin: 8px 0 6px;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.5;
}

/* global.css 第 69 行有 ul,ol{list-style:none} 的全站重置（那是给菜单用的），
   Markdown 生成的列表必须把它抢回来，否则圆点/序号全都不见 */
.markdown-body :deep(ul) {
  padding-left: 20px;
  margin: 4px 0 8px;
  list-style: disc;
}

.markdown-body :deep(ol) {
  padding-left: 20px;
  margin: 4px 0 8px;
  list-style: decimal;
}

.markdown-body :deep(li) {
  margin: 2px 0;
}

.markdown-body :deep(code) {
  padding: 1px 5px;
  font-family: Consolas, Monaco, monospace;
  font-size: 13px;
  background-color: rgba(0, 21, 41, 0.06);
  border-radius: 4px;
}

/* 代码块：横向可滚，长行不会把气泡撑出屏幕 */
.markdown-body :deep(pre) {
  padding: 10px 12px;
  margin: 4px 0 8px;
  overflow-x: auto;
  background-color: #f5f7fa;
  border-radius: 8px;
}

.markdown-body :deep(pre code) {
  padding: 0;
  background-color: transparent;
}

/* 表格：display:block + overflow-x 是窄抽屉（420px）里的保命写法，
   否则列一多就把整个面板横向撑开，连输入框都跟着变形 */
.markdown-body :deep(table) {
  display: block;
  max-width: 100%;
  margin: 4px 0 10px;
  overflow-x: auto;
  font-size: 13px;
  border-collapse: collapse;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 4px 10px;
  text-align: left;
  word-break: break-word;
  border: 1px solid var(--color-border);
}

.markdown-body :deep(th) {
  font-weight: 600;
  background-color: rgba(245, 247, 250, 0.9);
}

.markdown-body :deep(a) {
  color: var(--color-accent);
  word-break: break-all;
}

.markdown-body :deep(blockquote) {
  padding-left: 10px;
  margin: 4px 0 8px;
  color: var(--color-text-secondary);
  border-left: 3px solid var(--color-border);
}

.markdown-body :deep(hr) {
  margin: 10px 0;
  border: none;
  border-top: 1px solid var(--color-border);
}

/* 模型如果输出图片语法，限制在气泡宽度内 */
.markdown-body :deep(img) {
  max-width: 100%;
  border-radius: 8px;
}
</style>
