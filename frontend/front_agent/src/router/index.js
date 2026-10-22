// 导入创建路由的两个核心 API：createRouter 组装路由实例，createWebHistory 指定 history 模式
import { createRouter, createWebHistory } from 'vue-router'
// 守卫要判断本地是否存有 token：token 的唯一读出口在 utils/auth.js
// getUserInfo 一并拿来做角色闸门（adminOnly 路由需要 role === 'admin'）
import { getToken, getUserInfo } from '@/utils/auth'

// 创建路由实例；文件末尾 export 给 main.js 通过 app.use(router) 挂载
const router = createRouter({
  // history 模式：URL 不带 #（如 http://localhost:5173/home）
  // import.meta.env.BASE_URL 是 Vite 内置变量，默认 '/'；部署到子目录时它等于部署基路径
  // 注意：history 模式部署后，服务器需把未命中静态文件的请求回退到 index.html，否则直接访问子路由会 404
  history: createWebHistory(import.meta.env.BASE_URL),
  // 路由表：数组，每一项是一条路由规则；地址变化时从上往下匹配
  routes: [
    {
      // 一级路由路径：'/' 即站点根地址，匹配后渲染外壳 Layout.vue
      path: '/',
      // redirect：访问 '/' 时自动改址到 '/home'，从而命中下面的子路由
      // 因为子路由 path 是 'home' 而不是 ''，'/' 本身没有对应的内容组件，不重定向就会只剩空外壳
      redirect: '/manager/home',
    },
    {
      // 登录页：独立顶级路由，不套 Layout 外壳（未登录不应看到顶栏/侧边栏）
      path: '/login',
      name: 'Login',
      meta: { title: '登录' },
      component: () => import('@/views/Login.vue'),
    },
    {
      // 注册页：与登录页同级，同样不套 Layout 外壳
      path: '/register',
      name: 'Register',
      meta: { title: '注册' },
      component: () => import('@/views/Register.vue'),
    },
    {
      path: '/manager',
      name: 'Layout',
      component: () => import('@/layout/Layout.vue'),
      // 子路由数组：子路由匹配成功后，渲染进 Layout.vue 内部的 <router-view />（不是 App.vue 那个）
      children: [
        {
          // 子路由路径不以 / 开头，最终地址 = 父路径 + 'home' = /home
          // （对比另一种写法 path: ''：空串表示"父路径本身"，页面地址就是 /，此时不需要 redirect）
          path: 'home',
          // 路由名：path 的别名，用于 router.push({ name: 'Home' }) 这类编程式导航，比写死路径字符串安全
          name: 'Home',
          // meta 是自定义信息包：这里放页面标题；Layout 顶栏读 route.meta.title 显示当前页名
          meta: { title: '系统首页' },
          // 页面内容组件：只负责内容本身，外壳由 Layout 提供
          component: () => import('@/views/Home.vue'),
        },
        {
          // 子路由路径不以 / 开头，最终地址 = 父路径 + 'home' = /home
          // （对比另一种写法 path: ''：空串表示"父路径本身"，页面地址就是 /，此时不需要 redirect）
          path: 'lablist',
          // 路由名：path 的别名，用于 router.push({ name: 'Home' }) 这类编程式导航，比写死路径字符串安全
          name: 'Lablist',
          // meta 是自定义信息包：这里放页面标题；Layout 顶栏读 route.meta.title 显示当前页名
          meta: { title: '实验室列表' },
          // 页面内容组件：只负责内容本身，外壳由 Layout 提供
          component: () => import('@/views/Lablist.vue'),
        },
        {
          // 子路由路径不以 / 开头，最终地址 = 父路径 + 'home' = /home
          // （对比另一种写法 path: ''：空串表示"父路径本身"，页面地址就是 /，此时不需要 redirect）
          path: 'lab',
          // 路由名：path 的别名，用于 router.push({ name: 'Home' }) 这类编程式导航，比写死路径字符串安全
          name: 'Lab',
          // meta 是自定义信息包：这里放页面标题；Layout 顶栏读 route.meta.title 显示当前页名
          meta: { title: '实验室管理' },
          // 页面内容组件：只负责内容本身，外壳由 Layout 提供
          component: () => import('@/views/Lab.vue'),
        },
                {
          // 子路由路径不以 / 开头，最终地址 = 父路径 + 'home' = /home
          // （对比另一种写法 path: ''：空串表示"父路径本身"，页面地址就是 /，此时不需要 redirect）
          path: 'labequipment',
          // 路由名：path 的别名，用于 router.push({ name: 'Home' }) 这类编程式导航，比写死路径字符串安全
          name: 'LabEquipment',
          // meta 是自定义信息包：这里放页面标题；Layout 顶栏读 route.meta.title 显示当前页名
          meta: { title: '查看实验室设备' },
          // 页面内容组件：只负责内容本身，外壳由 Layout 提供
          component: () => import('@/views/LabEquipment.vue'),
        },
        {
          // 子路由路径不以 / 开头，最终地址 = 父路径 + 'home' = /home
          // （对比另一种写法 path: ''：空串表示"父路径本身"，页面地址就是 /，此时不需要 redirect）
          path: 'equipment',
          // 路由名：path 的别名，用于 router.push({ name: 'Home' }) 这类编程式导航，比写死路径字符串安全
          name: 'Equipment',
          // meta 是自定义信息包：这里放页面标题；Layout 顶栏读 route.meta.title 显示当前页名
          meta: { title: '实验室设备管理' },
          // 页面内容组件：只负责内容本身，外壳由 Layout 提供
          component: () => import('@/views/Equipment.vue'),
        },
        {
          // 子路由路径不以 / 开头，最终地址 = 父路径 + 'home' = /home
          // （对比另一种写法 path: ''：空串表示"父路径本身"，页面地址就是 /，此时不需要 redirect）
          path: 'myreservation',
          // 路由名：path 的别名，用于 router.push({ name: 'Home' }) 这类编程式导航，比写死路径字符串安全
          name: 'MyReservation',
          // meta 是自定义信息包：这里放页面标题；Layout 顶栏读 route.meta.title 显示当前页名
          meta: { title: '我的预约' },
          // 页面内容组件：只负责内容本身，外壳由 Layout 提供
          component: () => import('@/views/MyReservation.vue'),
        },
        {
          // 子路由路径不以 / 开头，最终地址 = 父路径 + 'home' = /home
          // （对比另一种写法 path: ''：空串表示"父路径本身"，页面地址就是 /，此时不需要 redirect）
          path: 'auditreservation',
          // 路由名：path 的别名，用于 router.push({ name: 'Home' }) 这类编程式导航，比写死路径字符串安全
          name: 'AuditReservation',
          // meta 是自定义信息包：这里放页面标题；Layout 顶栏读 route.meta.title 显示当前页名
          meta: { title: '预约审核' },
          // 页面内容组件：只负责内容本身，外壳由 Layout 提供
          component: () => import('@/views/AuditReservation.vue'),
        },
        {
          // 子路由路径不以 / 开头，最终地址 = 父路径 + 'home' = /home
          // （对比另一种写法 path: ''：空串表示"父路径本身"，页面地址就是 /，此时不需要 redirect）
          path: 'aichat',
          // 路由名：path 的别名，用于 router.push({ name: 'Home' }) 这类编程式导航，比写死路径字符串安全
          name: 'AiChat',
          // meta 是自定义信息包：这里放页面标题；Layout 顶栏读 route.meta.title 显示当前页名
          meta: { title: 'Ai助手' },
          // 页面内容组件：只负责内容本身，外壳由 Layout 提供
          component: () => import('@/views/AIChat.vue'),
        },
        {
          // 知识库管理：仅管理员可见（菜单加了 v-if，接口本身由后端 CurrentAdmin 把关）
          path: 'knowledge',
          name: 'Knowledge',
          meta: { title: '知识库管理' },
          component: () => import('@/views/Knowledge.vue'),
        },
        {
          // AI 供应商配置：仅管理员。adminOnly 让下面的全局守卫按角色再挡一道
          // （菜单 v-if 只是"看不见"，手输地址仍能进来，所以角色守卫是必要的）
          path: 'aiconfig',
          name: 'AIConfig',
          meta: { title: 'AI模型配置', adminOnly: true },
          component: () => import('@/views/AIConfig.vue'),
        },
        {
          // AI 用量与花费：从配置页拆出来的独立只读页，同样仅管理员
          path: 'aiusage',
          name: 'AIUsage',
          meta: { title: 'AI用量花费', adminOnly: true },
          component: () => import('@/views/AIUsage.vue'),
        },
        {
          // 子路由路径不以 / 开头，最终地址 = 父路径 + 'home' = /home
          // （对比另一种写法 path: ''：空串表示"父路径本身"，页面地址就是 /，此时不需要 redirect）
          path: 'users',
          // 路由名：path 的别名，用于 router.push({ name: 'Home' }) 这类编程式导航，比写死路径字符串安全
          name: 'Users',
          // meta 是自定义信息包：这里放页面标题；Layout 顶栏读 route.meta.title 显示当前页名
          meta: { title: '用户管理' },
          // 页面内容组件：只负责内容本身，外壳由 Layout 提供
          component: () => import('@/views/Users.vue'),
        },
        {
          // 个人信息页：入口在 Layout 顶栏右下拉的"个人信息"项，渲染进 Layout 的出口
          path: 'profile',
          name: 'Profile',
          meta: { title: '个人信息' },
          component: () => import('@/views/Profile.vue'),
        },
        {
          path: 'password',
          name: 'Password',
          meta: { title: '修改密码' },
          component: () => import('@/views/Password.vue'),
        },
        // 以后新增页面的模板（三步：建 views 文件 → 这里加一条路由 → Layout 菜单加一个 el-menu-item）：
        // {
        //   path: 'labs', // 最终地址 = /labs
        //   name: 'Labs',
        //   meta: { title: '实验室管理' },
        //   component: () => import('@/views/Labs.vue'),
        // },
      ],
    },
  ],
})
// 路由守卫
router.beforeEach((to, from) => {
  const token = getToken()
  if (to.path === '/login' || to.path === '/register') {
    // 如果访问的是登录页或注册页，直接放行
    return true
  } else {
    // 访问其他页面，检查是否有 token
    if (!token) return '/login' // 无 token 一律去登录页
    // 角色闸门：meta.adminOnly 的页面只有 admin 能进。
    // 菜单的 v-if 只是"看不见"，学生手敲 /manager/aiconfig 仍然能加载组件，
    // 所以这一道必须在前端拦一下（后端本来也会 403，这里省掉一次必失败的请求）
    if (to.meta.adminOnly && getUserInfo()?.role !== 'admin') return '/manager/home'
    return true
  }
})
// 导出路由实例，供 main.js import 后挂载
export default router
