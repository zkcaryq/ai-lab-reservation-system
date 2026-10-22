import axios from 'axios'
import { ElMessage } from 'element-plus'

import router from '@/router'
import { getToken, logout } from '@/utils/auth'

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 10000,
})

request.interceptors.request.use(
  (config) => {
    const token = getToken()

    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }

    return config
  },
  (error) => Promise.reject(error),
)

request.interceptors.response.use(
  (response) => {
    // 图片来源接口返回Blob而不是统一JSON。它已经通过HTTP 2xx表达成功，
    // 这里直接返回二进制对象，不能继续读取不存在的data.code。
    if (response.config.responseType === 'blob') {
      return response.data
    }

    // response.data才是后端统一响应：
    // { code, message, data }
    const data = response.data

    // 接受所有2xx成功码：
    // 200：查询、登录、普通修改成功
    // 201：注册等资源创建成功
    const isSuccess = data.code >= 200 && data.code < 300

    // 这是防御性检查。
    // 正常情况下，后端真实HTTP状态码与JSON中的code应该保持一致，
    // 因此4xx/5xx一般会直接进入下面的错误回调。
    if (!isSuccess) {
      ElMessage.error(data.message || '请求失败！Ovo')

      // 如果某个接口错误地返回HTTP 200、JSON code 401，
      // 这里仍然能够清除已经失效的登录状态。
      if (data.code === 401) {
        logout()

        if (router.currentRoute.value.path !== '/login') {
          router.push('/login')
        }
      }

      // 必须reject，避免页面继续执行成功逻辑。
      return Promise.reject(data)
    }

    // 剥掉Axios响应外壳。
    return data
  },

  (error) => {
    // 有response说明服务器已经响应，只是HTTP状态码不是2xx。
    if (error.response) {
      const status = error.response.status
      const data = error.response.data

      if (status === 401) {
        // 401统一提示一次，避免原代码连续弹出两条错误消息。
        ElMessage.error(data?.message || '登录状态已失效，请重新登录')

        logout()

        if (router.currentRoute.value.path !== '/login') {
          router.push('/login')
        }
      } else {
        // 400、403、409、422、500等错误统一显示后端消息。
        ElMessage.error(data?.message || '请求失败！Ovo')
      }
    } else if (error.code === 'ECONNABORTED') {
      // Axios超时通常没有error.response，单独提示更准确。
      ElMessage.error('请求超时，请稍后重试！Ovo')
    } else {
      // 可能是断网、后端未启动、域名错误或浏览器拦截。
      ElMessage.error('网络异常，请检查后端服务和网络连接！Ovo')
    }

    return Promise.reject(error)
  },
)

export default request
