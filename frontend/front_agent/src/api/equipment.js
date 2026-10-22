// 设备相关接口：与 lab/user 同构——一个分页查询 + 新增/修改/删除三个写接口
// 契约来源（只读核查 2026-10-09）：backend/app/api/routes/equipment_router.py
// 注意：后端修改用 PATCH（部分更新），不是教程写的 PUT；实测 /api/equipment/list 返回 401 说明路由已生效
import request from '@/utils/request'

// 分页查询设备：GET /api/equipment/list
// params = { page, page_size, keywords?, lab_id? }
// lab_id 传 null/undefined 时 axios 不会把它拼进查询串（等价于"不按实验室筛选"），所以别手动赋 ''
export function getEquipmentPageListApi(params) {
  return request({
    url: '/api/equipment/list',
    method: 'get',
    params,
  })
}

// 新增设备：POST /api/equipment（后端返回 HTTP 201 + JSON code 201，页面判定统一用 2xx 区间）
// data = { lab_id, name, description?, img?, spec?, quantity, status }
export function createEquipmentApi(data) {
  return request({
    url: '/api/equipment',
    method: 'post',
    data,
  })
}

// 修改设备：PATCH /api/equipment/{id}
// 只传本次要改的字段白名单；id 走路径、lab_name 是后端关联出来的只读字段，都不进请求体
export function updateEquipmentApi(equipmentId, data) {
  return request({
    url: `/api/equipment/${equipmentId}`,
    method: 'patch',
    data,
  })
}

// 删除设备：DELETE /api/equipment/{id}
export function deleteEquipmentApi(equipmentId) {
  return request({
    url: `/api/equipment/${equipmentId}`,
    method: 'delete',
  })
}
