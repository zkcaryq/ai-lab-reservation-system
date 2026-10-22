// AI 对话的共享状态：模块级 ref = 全站唯一一条对话（与 utils/user.js 的 userInfo 同一套路）
// 为什么必须放模块级：现在有两个入口要用它——「Ai助手」整页 和 右下角悬浮气泡。
// 各自存一份的话，页面里问过的内容气泡看不到、气泡里的上下文页面也不知道，两边会"各说各话"。
//
// 会话上下文口径（2026-10-20 与后端核对）：
//   后端 ChatRequest 收 { message, session_id }，模型与思考等级由管理员配置，
//   ChatResponse 返回 { message, session_id, model, usage, sources }。
//   MiniMax 的 Responses API 不支持 previous_response_id，多轮历史由后端从数据库
//   读 messages 拼接，所以前端只负责保存并回传 session_id。
//   传输方式：纯文本走 SSE（POST /api/ai/chat/stream，事件 status/tool_start/
//   tool_end/token/done/error）；带图片那一轮后端没有流式版本，仍走整包接口。
import { computed, reactive, ref } from 'vue'
// 单轮对话接口（api/ai.js 里已把 timeout 单独放宽到 60 秒）
import {
  cancelAiActionApi,
  chatStreamApi,
  chatWithImageApi,
  clearAiSessionApi,
  confirmAiActionApi,
  deleteAiSessionApi,
  getAiModelsApi,
  getAiSessionDetailApi,
  getAiSessionListApi,
  getAiSourceImageApi,
  renameAiSessionApi,
} from '@/api/ai'

// 欢迎语：只作显示层的第一条，不参与发送给模型
const GREETING =
  '您好，我是实验室助手。你可以问我怎么预约、怎么取消、开放时间这类问题，' +
  '也可以问现在有哪些开放的实验室、某个实验室有哪些设备。' +
  '需要预约时我会先把信息整理成一张确认卡片，你点「确认预约」后才会真正提交。'

// 消息 id 只用于列表渲染的 :key（会话内容本身在数据库里），比 :key="index" 稳
let uid = 0
const nextId = () => ++uid

// ===== 模块级共享状态：任何组件调 useAiChat() 拿到的都是下面这些 ref =====
const messages = ref([{ id: nextId(), role: 'assistant', content: GREETING }])
const sessionId = ref(null) // 当前会话 id；null = 还没落库的新对话
const loading = ref(false) // 发送中：两个入口共用同一个"忙"标记，避免并发提问

// 会话列表 / 模型面板状态：同样是模块级，两个入口共享一份
const sessions = ref([])
// 模型白名单只用来查"当前这个模型的窗口有多大、支不支持图片"，
// 聊天页不提供模型/思考层级选择——那归管理员在「AI模型配置」页里设
const models = ref([])
// 服务端实际用的模型，来自响应的 data.model（不是前端选的）
const activeModel = ref(null)
// 最近一轮的 token 用量。注意：后端 usage.input_tokens 已经包含整段历史，
// 所以"上下文占用"直接看最近一轮即可，把各轮相加会重复计算。
const lastUsage = ref(null)

// 组合式函数：组件里 const { messages, loading, send } = useAiChat()
export function useAiChat() {
  const selectedModel = computed(
    () => models.value.find((item) => item.id === activeModel.value) ?? null
  )
  // 上下文窗口：模型信息还没拿到时返回 0，模板据此不画进度条
  const contextWindow = computed(() => selectedModel.value?.context_window ?? 0)
  // 是否支持图片输入：以图提问按钮据此禁用（当前白名单两款都是 true）
  const supportsVision = computed(() => selectedModel.value?.vision !== false)

  // 释放一批消息里挂着的 Blob Object URL（图片与知识来源都是本地临时地址）
  function releaseBlobUrls(list) {
    for (const message of list) {
      if (message.imageObjectUrl) URL.revokeObjectURL(message.imageObjectUrl)
      for (const source of message.sources ?? []) {
        if (source.imageObjectUrl) URL.revokeObjectURL(source.imageObjectUrl)
      }
    }
  }

  // 知识来源里的图片要单独带 Token 请求，转成 Blob URL 才能显示
  async function loadSourceImages(sources = []) {
    const sourceResults = await Promise.allSettled(
      sources.map(async (source) => {
        if (!source.image_url) return { ...source, imageObjectUrl: null }
        const blob = await getAiSourceImageApi(source.chunk_id)
        return { ...source, imageObjectUrl: URL.createObjectURL(blob) }
      }),
    )
    return sourceResults
      .filter((result) => result.status === 'fulfilled')
      .map((result) => result.value)
  }

  // ===== 模型元信息 =====
  // 拉白名单只为拿 context_window / vision 这些展示信息；
  // 用哪个模型由管理员在配置页决定，前端不选、也不往 chat 请求里塞 model
  async function loadModels() {
    try {
      const res = await getAiModelsApi()
      if (res.code >= 200 && res.code < 300) {
        models.value = res.data?.models ?? []
      }
    } catch {
      // 提示归 request.js 拦截器；拿不到元信息只是不显示进度条，不影响提问
    }
  }

  // ===== 会话列表 =====
  async function loadSessions() {
    try {
      const res = await getAiSessionListApi()
      if (res.code >= 200 && res.code < 300) {
        sessions.value = res.data ?? []
      }
    } catch {
      // 提示归拦截器
    }
  }

  // 打开一个历史会话：后端只存 role + content，所以图片与知识来源不会回来；
  // 但预约草稿存在另一张表里，详情接口会连状态一起带回来，否则刷新后卡片就点不了了
  async function openSession(id) {
    if (!id || id === sessionId.value || loading.value) return
    try {
      const res = await getAiSessionDetailApi(id)
      if (res.code >= 200 && res.code < 300) {
        releaseBlobUrls(messages.value)
        const restored = (res.data?.messages ?? []).map((item) => ({
          id: nextId(),
          role: item.role === 'user' ? 'user' : 'assistant',
          content: item.content,
        }))
        // 卡片没有对应的正文消息（正文里也不该重复一遍参数），所以统一接在末尾
        for (const action of res.data?.pending_actions ?? []) {
          restored.push({
            id: nextId(),
            role: 'assistant',
            content: '',
            pendingAction: { ...action },
          })
        }
        messages.value = restored
        sessionId.value = id
        lastUsage.value = null
      }
    } catch {
      // 提示归拦截器：404 = 会话不存在或不属于当前用户
    }
  }

  // 新对话：只重置本地状态，后端要等第一轮成功后才建会话（标题取首条提问前30字）
  function newSession() {
    if (loading.value) return
    releaseBlobUrls(messages.value)
    messages.value = [{ id: nextId(), role: 'assistant', content: GREETING }]
    sessionId.value = null
    lastUsage.value = null
  }

  // 清空当前会话：已落库的要先让后端删消息，成功后再清本地——
  // 只清本地会留下"界面空了、后端还在攒历史"的错位
  async function clear() {
    if (loading.value) return
    if (sessionId.value) {
      try {
        await clearAiSessionApi(sessionId.value)
      } catch {
        return // 后端没清成功就不动本地，避免两边不一致
      }
      loadSessions()
    }
    newSession()
  }

  // 删除整个会话（列表项上的删除）；删的正是当前会话时顺手开一个新对话
  async function removeSession(id) {
    if (!id || loading.value) return
    try {
      await deleteAiSessionApi(id)
    } catch {
      return
    }
    if (id === sessionId.value) newSession()
    await loadSessions()
  }

  // 改标题：成功后只就地改列表里那一行的 title，不必重拉整个列表。
  // 返回值给组件决定要不要弹"已更新"，store 本身不碰 UI
  async function renameSession(id, title) {
    if (!id || !title) return false
    try {
      const res = await renameAiSessionApi(id, title)
      if (!(res.code >= 200 && res.code < 300)) return false
      const item = sessions.value.find((session) => session.id === id)
      if (item) item.title = title
      return true
    } catch {
      // 提示归 request.js 拦截器（404 = 会话不存在或不属于本人）
      return false
    }
  }

  // 把一轮回答的响应字段落到某条助手消息上。整包(/chat、/chat/image)和
  // 流式(/chat/stream 的 done 事件)共用同一份收尾逻辑，避免两条路径行为漂移。
  // 流式 token 用于实时打字效果；done 中的 message 是后端最终落库正文。
  // Agent 多轮工具调用可能产生中间文本，因此 done 时仍要用规范正文校正一次。
  async function applyTurnResult(target, payload, { withContent = true } = {}) {
    if (withContent) target.content = payload?.message ?? '（这轮没有返回内容）'
    target.sources = await loadSourceImages(payload?.sources)
    target.usage = payload?.usage ?? null
    target.model = payload?.model ?? null
    target.usedTools = payload?.used_tools ?? []
    // 后端把整轮耗时一并返回，气泡底部显示“用时 x.x 秒”
    target.durationMs = payload?.duration_ms ?? null

    const action = payload?.pending_action ?? null
    if (action) {
      // 实时响应的 PendingReservationAction 没有 status（只有历史恢复用的
      // SessionPendingAction 有）。缺省就是刚建好的待确认，不补默认值卡片会没按钮。
      if (!action.status) action.status = 'pending'
      // 后端 prepare_reservation_action 会把同会话旧草稿改成 cancelled；本地不同步
      // 就会出现两张都能点的卡片，点旧的只会吃到 409。
      for (const earlier of messages.value) {
        if (earlier !== target && earlier.pendingAction?.status === 'pending') {
          earlier.pendingAction.status = 'cancelled'
        }
      }
    }
    target.pendingAction = action

    if (payload?.session_id) {
      const isFirstTurn = sessionId.value === null
      sessionId.value = payload.session_id
      // 首轮后端才创建会话并生成标题，列表要刷一次才能看到
      if (isFirstTurn) loadSessions()
    }
    // 进度条的分母（context_window）按服务端实际用的模型查
    if (payload?.model) activeModel.value = payload.model
    lastUsage.value = payload?.usage ?? null
  }

  // SSE 发送：先插入一条空的助手消息，事件到达时一点点改它的字段。
  // 必须用 reactive 包这个对象 —— 普通对象 push 进数组后再改属性，
  // 视图可能不更新（数组只追踪"增删"，嵌套对象的属性要靠 reactive 代理）。
  async function runStream(content) {
    const assistant = reactive({
      id: nextId(),
      role: 'assistant',
      content: '',
      sources: [],
      status: '正在思考…',
      steps: [],
      usage: null,
      model: null,
      usedTools: [],
      pendingAction: null,
    })
    messages.value.push(assistant)

    // done 事件的载荷先接住，等流结束再统一处理：
    // 加载知识来源图片要 await，而 onEvent 是同步回调，在里面 await 不干净。
    let done = null
    let streamError = null

    await chatStreamApi({ message: content, session_id: sessionId.value }, (evt) => {
      if (evt.type === 'status') {
        assistant.status = evt.message || '正在思考…'
      } else if (evt.type === 'tool_start') {
        const label = evt.label || evt.name || '工具'
        assistant.status = `正在${label}…`
        assistant.steps.push(`开始：${label}`)
      } else if (evt.type === 'tool_end') {
        const label = evt.label || evt.name || '工具'
        assistant.status = `${label}完成`
        assistant.steps.push(`完成：${label}`)
      } else if (evt.type === 'token') {
        // 打字机：追加而不是覆盖；一开始出字就清掉状态文案，避免两行叠着晃眼
        assistant.content += evt.content || ''
        assistant.status = ''
      } else if (evt.type === 'done') {
        done = evt
      } else if (evt.type === 'error') {
        streamError = evt.message || 'AI助手出错了'
      }
    })

    if (done) await applyTurnResult(assistant, done)

    if (streamError) {
      assistant.error = true
      if (!assistant.content) assistant.content = streamError
    }
    // 流跑完但没收到 done（连接被切断/网关吞了响应）：给个可读的收尾，
    // 不能留一个"有半截正文、状态还挂着正在思考"的气泡
    if (!done && !streamError) {
      assistant.error = true
      if (!assistant.content) assistant.content = '连接中断了，这一轮没有完成，请重新提问。'
    }
    assistant.status = ''
  }

  // 发送一轮：入队用户消息 → 请求 → 入队回答（或错误气泡）→ 保存 session_id
  // 返回值只告诉调用方"有没有发出去"，输入框清空由调用方决定（发成功/失败都清，见 ChatPanel）
  async function send(text, imageFile = null) {
    const content = (text ?? '').trim() || (imageFile ? '请根据这张图片回答问题' : '')
    // 空输入不发；loading 期间再按 Enter 也不发（防连点重复计费）
    if (!content || loading.value) return false

    messages.value.push({
      id: nextId(),
      role: 'user',
      content,
      imageObjectUrl: imageFile ? URL.createObjectURL(imageFile) : null,
    })
    loading.value = true

    try {
      if (imageFile) {
        // 图片接口是 multipart 表单：字段名必须与后端 Form 一致。
        // 后端没有图片的流式版本，所以带图这一轮仍走整包返回。
        const formData = new FormData()
        formData.append('file', imageFile)
        formData.append('message', content)
        if (sessionId.value) formData.append('session_id', String(sessionId.value))
        const res = await chatWithImageApi(formData)
        if (res.code >= 200 && res.code < 300) {
          const assistant = { id: nextId(), role: 'assistant', content: '', sources: [] }
          messages.value.push(assistant)
          await applyTurnResult(assistant, res.data)
        }
      } else {
        // 纯文本走 SSE：过程可见 + 正文逐字出现
        await runStream(content)
      }
    } catch {
      // 拦截器已经弹了后端原文提示，但 toast 几秒就消失；
      // 对话界面没有"重拉列表"能兜底，所以这里额外留一条气泡，让失败在会话里是可见的
      messages.value.push({
        id: nextId(),
        role: 'assistant',
        content: '抱歉，这一轮没能回答上。可能是超时或服务异常，稍等一下再问一次。',
        error: true,
      })
    } finally {
      loading.value = false
    }
    return true
  }

  // 确认草稿 = 真正写进 reservations 表。失败时不改本地状态，卡片保持可点，
  // 后端 409/404 的原文由拦截器弹出，用户看得懂为什么没成
  async function confirmPendingAction(message) {
    const action = message?.pendingAction
    if (!action || action.status !== 'pending' || action.submitting) return
    action.submitting = true
    try {
      const res = await confirmAiActionApi(action.action_id)
      if (res.code >= 200 && res.code < 300) {
        action.status = 'completed'
        action.reservation_id = res.data?.reservation_id ?? null
        // 后端对重复确认是幂等返回原预约，不是报错；标一下好区分"刚提交"和"早就提交过了"
        action.duplicate = Boolean(res.data?.already_confirmed)
        action.resultMessage = res.message || '预约已提交，请等待审核！'
      }
    } catch {
      // 提示归拦截器
    } finally {
      action.submitting = false
    }
  }

  // 取消草稿：后端只允许取消 pending，其它状态会 409
  async function cancelPendingAction(message) {
    const action = message?.pendingAction
    if (!action || action.status !== 'pending' || action.submitting) return
    action.submitting = true
    try {
      const res = await cancelAiActionApi(action.action_id)
      if (res.code >= 200 && res.code < 300) {
        action.status = 'cancelled'
        action.resultMessage = res.message || '预约草稿已取消！'
      }
    } catch {
      // 提示归拦截器
    } finally {
      action.submitting = false
    }
  }

  return {
    messages,
    loading,
    sessionId,
    sessions,
    models,
    activeModel,
    lastUsage,
    selectedModel,
    contextWindow,
    supportsVision,
    send,
    clear,
    loadModels,
    loadSessions,
    openSession,
    newSession,
    removeSession,
    renameSession,
    confirmPendingAction,
    cancelPendingAction,
  }
}
