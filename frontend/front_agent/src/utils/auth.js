// 本文件职责：登录凭证（token）与用户信息在浏览器本地的"唯一读写出口"
// 谁要用 token / 用户信息都从这里 import，不要在页面里散落写 localStorage.getItem('token')

// localStorage 的键名集中定义成常量：以后要改键名，只改这一处，不会漏改
const TOKEN_KEY = 'token' // 存 JWT 字符串用的键
const USER_KEY = 'userInfo' // 存当前用户信息（对象）用的键

// 读 token：localStorage 里没有这个键时返回 null，调用方用 if (token) 判断即可
export function getToken() {
  return localStorage.getItem(TOKEN_KEY) // getItem 永远返回"字符串或 null"，不会返回对象
}

// 写 token：登录成功后调用；JWT 本身就是字符串，直接存
export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token) // 同名键再次 setItem 会覆盖旧值（没有"追加"语义）
}

// 删 token：退出登录、或后端返回 401 表示登录失效时调用
export function removeToken() {
  localStorage.removeItem(TOKEN_KEY)
}

// 读用户信息：存进去时被序列化成了 JSON 字符串，所以取出来要 JSON.parse 还原成对象
export function getUserInfo() {
  const userInfo = localStorage.getItem(USER_KEY) // 先拿到原始字符串（没登录过则是 null）
  // 三元判断：字符串存在才解析；否则直接返回 null，避免对 null 做 JSON.parse 得到意外结果
  return userInfo ? JSON.parse(userInfo) : null
}

// 写用户信息：localStorage 只能存字符串，对象必须先 JSON.stringify 序列化
export function setUserInfo(userInfo) {
  localStorage.setItem(USER_KEY, JSON.stringify(userInfo)) // 传入对象 → 存成 JSON 字符串
}

// 删用户信息
export function removeUserInfo() {
  localStorage.removeItem(USER_KEY)
}

// 登出：token 和用户信息必须"成对清除"
// 只清 token 会留下"有用户名但没凭证"的半登录态，界面显示已登录、请求却带不上 Authorization
export function logout() {
  removeToken() // 第一步：删 token
  removeUserInfo() // 第二步：删用户信息
}
