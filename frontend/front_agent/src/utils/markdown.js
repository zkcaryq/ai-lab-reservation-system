// AI消息的Markdown渲染：marked负责解析，DOMPurify负责消毒。
// DOMPurify必须保留：marked不做任何安全过滤，模型输出或注入内容
// （<script>、onerror事件等）必须经过消毒才能进v-html。
import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({
  gfm: true, // 启用GFM表格等扩展语法
  breaks: true, // 单个\n也换行，匹配聊天气泡的阅读习惯
})

export function renderMarkdown(text) {
  return DOMPurify.sanitize(marked.parse(text ?? ''))
}
