// src/utils/url.js

/**
 * 将后端返回的相对资源路径转换成完整URL。
 */
export function resolveBackendUrl(path) {
  if (!path) {
    return ''
  }

  // 已经是完整URL时直接返回。
  if (/^https?:\/\//i.test(path)) {
    return path
  }

  // 开发环境使用后端地址；
  // 生产同域代理且变量为空时使用当前页面地址。
  const baseURL =
    import.meta.env.VITE_API_BASE_URL ||
    window.location.origin

  return new URL(path, baseURL).href
}