// 知识库文档管理接口：上传 / 列表 / 详情 / 分块预览 / 重新处理 / 启停 / 删除
// 契约来源（只读核查 2026-10-20）：backend/app/api/routes/knowledge_router.py
// 三条要点：
//   ① 前缀 /api/knowledge，七个端点全部 CurrentAdmin —— 学生调用一律 403
//   ② 上传与"重新处理"返回 HTTP 202（排队语义：OCR/Embedding 不在请求里做），
//      所以页面要能轮询状态，不能上传完就当它已经好了
//   ③ 大小/后缀限制来自 settings：MAX_KNOWLEDGE_FILE_BYTES=20MiB、
//      ALLOWED_KNOWLEDGE_EXTENSIONS=.docx/.pdf/.xlsx/.md/.zip/.jpg/.jpeg/.png/.webp
//      超了后端回 413，后缀不对回 415
import request from '@/utils/request'

// 上传知识文档：multipart/form-data，字段名固定是 file（后端 File() 按这个名字取）
// 大文件走网络慢，这里和 AI 一样把 timeout 放宽到 60 秒（实例默认只有 10 秒）
export function uploadKnowledgeDocumentApi(file) {
  const form = new FormData()
  form.append('file', file)
  return request({
    url: '/api/knowledge/documents',
    method: 'post',
    data: form,
    timeout: 60000,
  })
}

// 分页查询文档：GET /api/knowledge/documents
// params = { page, page_size, keywords?, status? }
// status 可选值 queued | processing | completed | failed；不传（null/undefined）= 全部
export function getKnowledgePageListApi(params) {
  return request({
    url: '/api/knowledge/documents',
    method: 'get',
    params,
  })
}

// 单个文档详情：GET /api/knowledge/documents/{id}
export function getKnowledgeDocumentApi(documentId) {
  return request({
    url: `/api/knowledge/documents/${documentId}`,
    method: 'get',
  })
}

// 分块预览：GET /api/knowledge/documents/{id}/chunks
// 后端只回预览字段（content/page_number/sheet_name/heading_path 等），不返回完整向量
export function getKnowledgeChunksApi(documentId) {
  return request({
    url: `/api/knowledge/documents/${documentId}/chunks`,
    method: 'get',
  })
}

// 重新处理（排队）：POST /api/knowledge/documents/{id}/reprocess，无请求体，返回 202
export function reprocessKnowledgeDocumentApi(documentId) {
  return request({
    url: `/api/knowledge/documents/${documentId}/reprocess`,
    method: 'post',
  })
}

// 启用 / 停用：PATCH /api/knowledge/documents/{id}/enabled，body { enabled: true|false }
export function updateKnowledgeEnabledApi(documentId, enabled) {
  return request({
    url: `/api/knowledge/documents/${documentId}/enabled`,
    method: 'patch',
    data: { enabled },
  })
}

// 删除文档：DELETE /api/knowledge/documents/{id}
export function deleteKnowledgeDocumentApi(documentId) {
  return request({
    url: `/api/knowledge/documents/${documentId}`,
    method: 'delete',
  })
}
