// 预约相关接口：提交 / 列表 / 取消 / 审核
// 契约来源（只读核查 2026-10-19）：backend/app/api/routes/reservation_router.py
// 两条实测结论：① 路径是单数 /api/reservation（复数会 404）；② 取消与审核是 **PATCH**，
// 教程写的 PUT 会被后端拒成 405（Method Not Allowed）——以我们后端的实际方法为准
import request from '@/utils/request'

// 提交预约：POST /api/reservation（登录用户即可，后端返回 HTTP 201 + JSON code 201）
// data = { lab_id, equipment_id?, date: 'YYYY-MM-DD', start_time: 'HH:mm', end_time: 'HH:mm', remark? }
// equipment_id 省略或 null = 只约实验室；user_id 永远不传（后端从 Token 取当前登录用户）
export function createReservationApi(data) {
  return request({
    url: '/api/reservation',
    method: 'post',
    data,
  })
}

// 预约分页列表：GET /api/reservation/list
// params = { page, page_size, status? }
// 身份过滤在后端做：学生只回自己的记录，管理员回全部——前端不要传 user_id、也不要自己判断角色
// status 传 null/undefined 时 axios 不拼该参数 = 看全部状态；筛待审核就传数字 0
export function getReservationPageListApi(params) {
  return request({
    url: '/api/reservation/list',
    method: 'get',
    params,
  })
}

// 取消预约：PATCH /api/reservation/{id}/cancel（无请求体，动作在路径里）
// 规则：仅本人、仅"待审核(0)"可取消，取消后 status=3；他人或已完成的状态会被后端拒
export function cancelReservationApi(reservationId) {
  return request({
    url: `/api/reservation/${reservationId}/cancel`,
    method: 'patch',
  })
}

// 审核预约：PATCH /api/reservation/{id}/audit，body { status: 1 通过 | 2 拒绝 }
// 仅管理员可调用（后端 CurrentAdmin），且只有"待审核(0)"的记录能被审
export function auditReservationApi(reservationId, status) {
  return request({
    url: `/api/reservation/${reservationId}/audit`,
    method: 'patch',
    data: { status },
  })
}
