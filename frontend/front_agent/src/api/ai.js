// 所有请求继续复用项目现有Axios实例，从而自动携带Bearer Token并统一处理错误。
import request from '@/utils/request'
// 流式接口用原生 fetch，不走 axios：它需要自己读 ReadableStream。
// Token 的唯一读出口仍在 utils/auth.js，不在这里碰 localStorage。
import { getToken } from '@/utils/auth'

/**
 * 向后端AI助手发送一轮消息。
 *
 * data形状（与后端 ChatRequest 一致）：
 *   { message: '怎么预约？', session_id: 12 }
 * 首轮 session_id 传 null，由后端建会话并在响应的 data.session_id 里返回；
 * 模型和思考等级只从管理员保存的数据库配置读取，普通聊天请求不能覆盖。
 */
export function chatApi(data) {
  return request({
    // request实例已经配置VITE_API_BASE_URL，这里只写后端相对路径。
    url: '/api/ai/chat',
    method: 'post',
    data,

    // 全局request.js是10秒；模型生成可能更久，本接口单独覆盖为60秒。
    // Axios会优先使用本次请求配置，不会修改其他接口的10秒超时。
    timeout: 60_000,
  })
}

/** 上传一张图片并进行多模态问答。FormData由浏览器自动生成multipart边界。 */
export function chatWithImageApi(data) {
  return request({
    url: '/api/ai/chat/image',
    method: 'post',
    data,
    timeout: 120_000,
  })
}

/** 以Blob读取受Bearer Token保护的知识来源图片。 */
export function getAiSourceImageApi(chunkId) {
  return request({
    url: `/api/ai/sources/${chunkId}/image`,
    method: 'get',
    responseType: 'blob',
    timeout: 30_000,
  })
}

// ===== 以下是管理员的「AI 供应商配置」接口（后端全部 CurrentUser + role=='admin' 双重把关） =====

/** 列出7个能力的当前配置；密钥由后端脱敏成 api_key_masked，永不下发明文。 */
export function getAiConfigListApi() {
  return request({
    url: '/api/ai/admin/configs',
    method: 'get',
  })
}

/**
 * 保存某个能力的配置。后端是 PUT（整条覆盖语义），不是本项目常见的 PATCH。
 * data形状：{ provider, model, base_url, api_key, reasoning_effort, is_active }
 * api_key 传 null 或空串 = 保留原密钥；reasoning_effort 传 null = 不设置。
 */
export function saveAiConfigApi(capability, data) {
  return request({
    url: `/api/ai/admin/configs/${capability}`,
    method: 'put',
    data,
  })
}

/**
 * 用「尚未保存」的鉴权信息去供应商查一次真实模型列表。
 * data形状：{ provider, base_url, api_key, capability }；key只在本次查询里用，后端不落库。
 * 这一步要出网访问 MiniMax/百炼，比本地查询慢，单独放宽到 30 秒。
 */
export function getProviderModelsApi(data) {
  return request({
    url: '/api/ai/provider/models',
    method: 'post',
    data,
    timeout: 30_000,
  })
}

/**
 * 按能力/供应商/模型聚合的最近30天用量与估算花费。
 * data = { days, items: [{capability, provider, model, calls, input_tokens,
 *          output_tokens, total_tokens, cost|null}], total_cost, priced_cost,
 *          currency, note }
 * cost 为 null 表示后端价格表里没有这个模型（该行未计入总花费）。
 */
export function getAiCostApi() {
  return request({
    url: '/api/ai/usage/cost',
    method: 'get',
  })
}

// ===== 会话与模型面板接口（后端 chat_services / ai_services 提供） =====

/** 可用模型白名单：data = { models: [{id,name,context_window,vision,reasoning,is_default}], default_model } */
export function getAiModelsApi() {
  return request({
    url: '/api/ai/models',
    method: 'get',
  })
}

/** 当前用户的会话摘要列表：data = [{id,title,updated_at}]，按最后活跃时间倒序。 */
export function getAiSessionListApi() {
  return request({
    url: '/api/ai/sessions',
    method: 'get',
  })
}

/** 单个会话详情：data = {id,title,messages:[{role,content}]}。历史只存文本，不含图片与来源。 */
export function getAiSessionDetailApi(sessionId) {
  return request({
    url: `/api/ai/sessions/${sessionId}`,
    method: 'get',
  })
}

/** 删除会话及其全部消息（后端级联删）。 */
export function deleteAiSessionApi(sessionId) {
  return request({
    url: `/api/ai/sessions/${sessionId}`,
    method: 'delete',
  })
}

/** 清空会话消息但保留会话本身（对应界面上的"清空会话"）。 */
export function clearAiSessionApi(sessionId) {
  return request({
    url: `/api/ai/sessions/${sessionId}/messages`,
    method: 'delete',
  })
}

/** 改会话标题：后端默认只取首条提问前30字，用户需要能改成自己认得的名字。 */
export function renameAiSessionApi(sessionId, title) {
  return request({
    url: `/api/ai/sessions/${sessionId}`,
    method: 'patch',
    data: { title },
  })
}

// ===== AI 预约草稿（pending_action）的确认与取消 =====
// 模型只准备草稿，真正写 reservations 表发生在 confirm 之后，所以这两个接口是
// "用户亲手提交"的那一步，必须带本人 Token，后端会校验草稿归属。

/**
 * 确认草稿并创建真实预约。
 * 重复确认不会报错：后端幂等返回原 reservation_id，并在 data.already_confirmed 里标出来。
 */
export function confirmAiActionApi(actionId) {
  return request({
    url: `/api/ai/actions/${actionId}/confirm`,
    method: 'post',
  })
}

/** 取消尚未确认的草稿；草稿已被确认/过期时后端返回 409。 */
export function cancelAiActionApi(actionId) {
  return request({
    url: `/api/ai/actions/${actionId}/cancel`,
    method: 'patch',
  })
}

/**
 * SSE 流式对话。每解析出一条事件就回调一次 onEvent(evt)。
 *
 * 为什么不用 EventSource：它只支持 GET，也不能带 Authorization 头，
 * 我们的接口是 POST + Bearer Token，所以只能用 fetch + ReadableStream。
 * 也不再受 axios 的 timeout 约束——连接会一直读到后端结束。
 */
export async function chatStreamApi(data, onEvent) {
  const baseURL = import.meta.env.VITE_API_BASE_URL || ''
  const token = getToken()

  const res = await fetch(`${baseURL}/api/ai/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(data),
  })

  if (res.status === 401) {
    // 登录失效单独抛，让调用方给出准确提示；这里不直接跳登录页，
    // 因为 api 层不知道路由状态，跳转统一交给 request.js 那套拦截器处理。
    const error = new Error('登录状态已失效，请重新登录')
    error.status = 401
    throw error
  }
  if (!res.ok || !res.body) {
    const error = new Error('流式接口请求失败')
    error.status = res.status
    throw error
  }

  const contentType = res.headers.get('content-type') || ''
  // 后端全局异常处理器可能把错误收成普通 JSON（HTTP 200 + {code,message}），
  // 这时绝不能按 SSE 去拆，否则用户只会看到一个空气泡。
  if (!contentType.includes('text/event-stream')) {
    const payload = await res.json().catch(() => null)
    const error = new Error(payload?.message || '流式接口返回异常')
    error.status = payload?.code ?? res.status
    throw error
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  // TCP 可能把一条 SSE 帧拆成两次送达，必须自己攒 buffer
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    // stream:true 让解码器记住"半个汉字"的字节，等下一块拼完整
    buffer += decoder.decode(value, { stream: true })

    // SSE 帧之间用空行分隔；最后一段可能不完整，pop 出来留到下一轮
    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''

    for (const frame of frames) {
      // 一帧里可能有多个字段行，我们只约定用 data:
      const line = frame
        .split('\n')
        .map((item) => item.trim())
        .find((item) => item.startsWith('data:'))
      if (!line) continue
      const raw = line.slice(5).trim()
      if (!raw || raw === '[DONE]') continue
      try {
        onEvent(JSON.parse(raw))
      } catch {
        // 脏数据或半包：跳过这一帧，等后面的完整帧
      }
    }
  }
}
