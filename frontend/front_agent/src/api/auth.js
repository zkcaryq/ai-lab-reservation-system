// API 模块：auth 相关接口集中定义在这里，页面不直接写 url / method，只调用函数
// request 是 utils/request.js 里封装好的 axios 实例：baseURL、timeout、两个拦截器都在它身上
import request from '@/utils/request';
// 登录接口：对应后端 POST /api/auth/login
// data = { username, password }，原样作为 JSON 请求体发出
export function loginApi(data) {
    // 返回值是 Promise：页面 await 后拿到 { code, message, data }（响应拦截器已剥壳）
    return request({
        url: "/api/auth/login",
        method: "post",
        data
    })
}
// 注册接口：对应后端 POST /api/auth/register
// data = { username, password }（name 可选）；confirmPassword 是前端比对字段，页面提交前需剔除
export function registerApi(data) {
    // 返回值是 Promise：页面 await 后拿到 { code, message, data }（响应拦截器已剥壳）
    return request({
        url: "/api/auth/register",
        method: "post",
        data
    })
}
