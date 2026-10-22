// 用户相关接口：与 auth 接口分文件——auth 管"登录态的获得"，user 管"登录者本人资料的读写"
import request from '@/utils/request'

export function getLabPageListApi(params) {
  return request({
    url: '/api/lab/list',
    method: 'get',
    params
  })
}
export function getLabApi(lab_id) {
  return request({
    url: `/api/lab/${lab_id}`,
    method: 'get'
  })
}
export function createLabApi(data) {
  return request({
    url: '/api/lab',
    method: 'post',
    data
  })
}
export function updateLabApi(labId, data) {
  return request({
    url: `/api/lab/${labId}`,
    method: 'patch',
    data
  })
}
export function deleteLabApi(labId) {
  return request({
    url: `/api/lab/${labId}`,
    method: 'delete'
  })
}
