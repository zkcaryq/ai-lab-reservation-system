// 用户相关接口：与 auth 接口分文件——auth 管"登录态的获得"，user 管"登录者本人资料的读写"
import request from '@/utils/request'

// 获取当前登录用户信息：GET /api/user/me（后端已从 /info 改名为 /me，前后端同步于 2026-10-08）
// 身份靠 Bearer 头识别（请求拦截器自动附加），GET 无请求体，所以不接收参数
export function getUserInfoApi() {
  // 返回值是 Promise：页面 await 后拿到 { code, message, data }（响应拦截器已剥壳）
  return request({
    url: '/api/user/me',
    method: 'get',
  })
}

// 更新个人信息：PATCH /api/user/me（PATCH 语义：只修改本次提交的字段；后端已从 /update 改名为 /me）
// data 只传可改字段 { name?, email?, phone?, avatar? }；username/role/status 后端 Schema 不收
export function updateUserInfoApi(data) {
  return request({
    url: '/api/user/me',
    method: 'patch',
    data,
  })
}
// 修改密码：PATCH /api/user/password（教程契约为 PUT，后端现状为 PATCH——定盘后只改这一行 method）
// data = { old_password, new_password }（snake_case 契约；confirmPassword 是前端本地比对字段，永不提交）
// 成功后页面需 logout() + 回登录页：密码已变，本地登录态语义过期（服务端旧 JWT 仍有效到过期）
export function updatePasswordApi(data) {
  return request({
    url: '/api/user/password',
    method: 'patch',
    data,
  })
}
export function getUserPageListApi(params) {
  return request({
    url: '/api/user/list',
    method: 'get',
    params
  })
}
export function createUserApi(data) {
  return request({
    url: '/api/user',
    method: 'post',
    data
  })
}
export function updateUserApi(userId, data) {
  return request({
    url: `/api/user/${userId}`,
    method: 'patch',
    data
  })
}
export function deleteUserApi(userId) {
  return request({
    url: `/api/user/${userId}`,
    method: 'delete'
  })
}
