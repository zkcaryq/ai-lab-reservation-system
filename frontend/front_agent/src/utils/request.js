import axios from 'axios'
import { getToken } from '@/utils/auth.js'
const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 10000,
})
service.interceptors.request.use(
  (config) => {
    const token = getToken()
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  },
)
service.interceptors.response.use((res) => {
  const data = res.data
  console.log("res:" ,res)
})
export default service
