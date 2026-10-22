<script setup>
// useRoute 返回响应式的"当前路由"对象：地址变化时 route.path / route.meta 自动更新，模板随之重新渲染
// useRouter 提供编程式导航：退出登录后 push 到 /login
import { useRoute, useRouter } from 'vue-router'
// computed：派生顶栏头像地址（相对路径 → 绝对 URL）；ref：AI 抽屉的开关
import { computed, ref } from 'vue'
// House 是侧边栏菜单图标；User 是顶栏无头像时的兜底图标
import { ChatDotRound, House, User } from '@element-plus/icons-vue'
// ElMessage 轻提示；ElMessageBox 确认弹窗（退出前的二次确认）
import { ElMessage, ElMessageBox } from 'element-plus'
// 退出登录要成对清除本地 token 与用户信息：logout 由 utils/auth.js 提供
import { logout } from '@/utils/auth'
// 顶栏要显示当前登录用户：userInfo 是 utils/user.js 里的模块级 ref，登录/保存后自动更新
import { useUser } from '@/utils/user'
// 后端存的是相对路径（/uploads/xxx.png），拼上后端地址浏览器才加载得到头像
import { resolveBackendUrl } from '@/utils/url'
// 全站粒子背景：复用登录/注册页同款组件（canvas 粒子连线 + 光斑 + 深色渐变）
import AuthBackground from '@/components/AuthBackground.vue'
// 右下角 AI 气泡：复用「Ai助手」整页的同一个面板与同一份会话状态
import ChatPanel from '@/components/ChatPanel.vue'
import { useAiChat } from '@/utils/aiChat'

// 解构出响应式 userInfo：值变化时本页模板自动重新渲染
const { userInfo } = useUser()
// 当前路由对象：菜单选中态用 route.path，顶栏页名用 route.meta.title
const route = useRoute()
const router = useRouter()
// 顶栏头像地址：无头像时 resolveBackendUrl 返回 ''，模板里 || undefined 让 el-avatar 走插槽兜底
const headerAvatarUrl = computed(() => {
  return resolveBackendUrl(userInfo.value?.avatar)
})
// ===== AI 助手悬浮气泡 =====
// 抽屉开关属于本页的局部 UI 状态；对话内容不在这里，在 utils/aiChat.js（与整页共用）
const aiDrawerVisible = ref(false)
// clear 与「Ai助手」页上的清空按钮是同一个动作，清完两边同时生效
const { clear: clearAiChat } = useAiChat()
// 已经在整页版里就不必再摆气泡：同一条对话显示两遍，还挡内容
const aiDockHidden = computed(() => route.path === '/manager/aichat')
// 用户下拉菜单统一入口：command 是被点击项的 command 值（profile / password / logout）
function handleCommand(command) {
  if (command === 'logout') {
    // ElMessageBox.confirm 返回 promise：点"退出"resolve，点"取消"reject
    // 后面的 .catch 必须写，否则取消时产生未处理的 promise rejection
    ElMessageBox.confirm('确定要退出登录吗？', '退出确认', {
      confirmButtonText: '退出',
      cancelButtonText: '取消',
      type: 'warning',
    })
      .then(() => {
        // 清除本地 token 与用户信息后送回登录页
        logout() // 调用登出函数，清除 token 等
        router.push('/login') // 跳转到登录页
        ElMessage.success('已退出登录!Ovo!') // 顶部轻提示
      })
      .catch(() => {
        // 用户点了取消：什么都不做，但必须 catch 掉 reject
      })
    return
  }
  if (command === 'profile') {
    // 个人信息页（真接口版）：直接导航过去，不再提示"开发中"
    router.push('/manager/profile')
    return
  }
  if (command === 'password') {
    // 修改密码页：直接导航过去
    router.push('/manager/password')
    return
  }
}
</script>

<template>
  <!-- el-container 是 Element Plus 的布局容器（flex）：直接子元素含 el-header 时自动纵向排列 -->
  <el-container class="layout-container">
    <!-- 粒子背景层：absolute 铺满 + z-index:-1 垫底（layout-container 已建堆叠上下文） -->
    <!-- 组件根元素透传 class：.layout-bg 只负责把层级压到内容之下 -->
    <AuthBackground class="layout-bg" />
    <!-- 顶部通栏 Header：横跨整行，高度与样式由下方 .layout-header 决定 -->
    <el-header class="layout-header">
      <!-- 左半区：品牌标识 + 当前页名 -->
      <div class="header-left">
        <!-- 品牌标识：logo 图片 + 系统名（图片自带设计，不再套渐变底色方块） -->
        <div class="brand">
          <!-- 模板里写 src="@/..." 会被 Vite 编译成资源 import，路径写错 build 直接报错 -->
          <img class="brand-logo" src="@/assets/imgs/logo-256.png" alt="系统 logo" />
          <!-- 系统名称，固定文案 -->
          <span class="brand-name">AI 智能实验室预约系统</span>
        </div>
        <!-- 仅当当前路由配置了 meta.title 时才渲染分隔线与页名（v-if 为假时整块不生成 DOM） -->
        <template v-if="route.meta.title">
          <!-- 竖直分隔线，纯装饰 -->
          <el-divider direction="vertical" />
          <!-- 当前页名：取自路由 meta.title，新增页面只需在路由表登记标题，此处自动显示 -->
          <span class="page-title">{{ route.meta.title }}</span>
        </template>
      </div>
      <!-- 右半区：当前登录用户的头像与姓名，数据来自共享 store（登录/保存后自动刷新） -->
      <div class="header-right">
        <!-- el-dropdown：默认插槽放"触发元素"，#dropdown 具名插槽放"菜单内容" -->
        <!-- @command：点击任意菜单项，把该项的 command 值传给回调，一个函数处理所有菜单项 -->
        <el-dropdown @command="handleCommand">
          <!-- 触发区：头像 + 用户名 + 下拉箭头，横向排列样式见 .user-trigger -->
          <div class="user-trigger">
            <!-- 头像：有 URL 显示图片；无头像时 src 为 undefined，渲染默认插槽的 User 图标兜底 -->
            <el-avatar size="small" :src="headerAvatarUrl || undefined">
              <el-icon><User /></el-icon>
            </el-avatar>
            <!-- 用户名：读共享 store 的真实姓名；可选链防 userInfo 为 null 时炸掉整个 Layout -->
            <span class="username">{{ userInfo?.name }}</span>
            <!-- 下拉箭头：ArrowDown 由 main.js 全量注册，可直接当组件用 -->
            <el-icon class="trigger-arrow"><ArrowDown /></el-icon>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <!-- command 属性：点击该项时传给 @command 回调的值 -->
              <el-dropdown-item command="profile">个人信息</el-dropdown-item>
              <el-dropdown-item command="password">修改密码</el-dropdown-item>
              <!-- divided：该项上方加分隔线，把"退出"与普通项在视觉上分开 -->
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-header>

    <!-- 第二层容器：直接子元素没有 el-header/el-footer，自动横向排列 = 左 aside + 右 main -->
    <el-container class="layout-body">
      <!-- 左侧边栏：width 固定 220px，深色背景由 .layout-aside 提供 -->
      <el-aside width="220px" class="layout-aside">
        <!-- el-menu 侧边菜单 -->
        <!-- router 属性：开启后点击菜单项自动 router.push(index)，index 即路由路径 -->
        <!-- :default-active：选中态绑定当前路径，直接输 URL 进入时选中态也正确 -->
        <!-- background-color 设透明，露出 .layout-aside 的深色底；文字色通过 CSS 变量传入 -->
        <el-menu
          router
          :default-active="route.path"
          class="aside-menu"
          background-color="transparent"
          text-color="var(--color-aside-text)"
          active-text-color="var(--color-aside-text-active)"
        >
          <!-- 菜单项：index='/home' 与路由表中的 /home 对应；以后加页面 = 在这里加一个 el-menu-item -->
          <el-menu-item index="/manager/home">
            <!-- 菜单项图标 -->
            <el-icon><Menu /></el-icon>
            <!-- #title 是具名插槽：放这里的内容成为菜单文字（侧边栏折叠时靠它切换为悬浮提示） -->
            <template #title>系统首页</template>
          </el-menu-item>
          <el-menu-item index="/manager/lablist" v-if="userInfo?.role === 'student'">
            <!-- 菜单项图标 -->
            <el-icon><OfficeBuilding /></el-icon>
            <!-- #title 是具名插槽：放这里的内容成为菜单文字（侧边栏折叠时靠它切换为悬浮提示） -->
            <template #title>实验室列表</template>
          </el-menu-item>
          <el-menu-item index="/manager/lab" v-if="userInfo?.role === 'admin'">
            <!-- 菜单项图标 -->
            <el-icon><House /></el-icon>
            <!-- #title 是具名插槽：放这里的内容成为菜单文字（侧边栏折叠时靠它切换为悬浮提示） -->
            <template #title>实验室管理</template>
          </el-menu-item>
          <el-menu-item index="/manager/equipment" v-if="userInfo?.role === 'admin'">
            <!-- 菜单项图标 -->
            <el-icon><Setting /></el-icon>
            <!-- #title 是具名插槽：放这里的内容成为菜单文字（侧边栏折叠时靠它切换为悬浮提示） -->
            <template #title>实验室设备管理</template>
          </el-menu-item>
          <el-menu-item index="/manager/users" v-if="userInfo?.role === 'admin'">
            <!-- 菜单项图标 -->
            <el-icon><User /></el-icon>
            <!-- #title 是具名插槽：放这里的内容成为菜单文字（侧边栏折叠时靠它切换为悬浮提示） -->
            <template #title>用户管理</template>
          </el-menu-item>
          <el-menu-item index="/manager/auditreservation" v-if="userInfo?.role === 'admin'">
            <!-- 菜单项图标 -->
            <el-icon><DocumentChecked /></el-icon>
            <!-- #title 是具名插槽：放这里的内容成为菜单文字（侧边栏折叠时靠它切换为悬浮提示） -->
            <template #title>预约审核</template>
          </el-menu-item>
          <el-menu-item index="/manager/myreservation" v-if="userInfo?.role === 'student'">
            <!-- 菜单项图标 -->
            <el-icon><Tickets /></el-icon>
            <!-- #title 是具名插槽：放这里的内容成为菜单文字（侧边栏折叠时靠它切换为悬浮提示） -->
            <template #title>我的预约</template>
          </el-menu-item>
          <el-menu-item index="/manager/aichat">
            <!-- 菜单项图标 -->
            <el-icon><ChatDotRound /></el-icon>
            <!-- #title 是具名插槽：放这里的内容成为菜单文字（侧边栏折叠时靠它切换为悬浮提示） -->
            <template #title>Ai助手</template>
          </el-menu-item>
          <el-menu-item index="/manager/knowledge" v-if="userInfo?.role === 'admin'">
            <!-- 菜单项图标 -->
            <el-icon><Reading /></el-icon>
            <!-- #title 是具名插槽：放这里的内容成为菜单文字（侧边栏折叠时靠它切换为悬浮提示） -->
            <template #title>知识库管理</template>
          </el-menu-item>
          <el-menu-item index="/manager/aiconfig" v-if="userInfo?.role === 'admin'">
            <!-- 菜单项图标：Tools 与"实验室设备管理"的 Setting 区分开 -->
            <el-icon><Tools /></el-icon>
            <!-- #title 是具名插槽：放这里的内容成为菜单文字（侧边栏折叠时靠它切换为悬浮提示） -->
            <template #title>AI模型配置</template>
          </el-menu-item>
          <el-menu-item index="/manager/aiusage" v-if="userInfo?.role === 'admin'">
            <!-- 菜单项图标：DataAnalysis 对应"用量/花费"这种统计页 -->
            <el-icon><DataAnalysis /></el-icon>
            <!-- #title 是具名插槽：放这里的内容成为菜单文字（侧边栏折叠时靠它切换为悬浮提示） -->
            <template #title>AI用量花费</template>
          </el-menu-item>
        </el-menu>
      </el-aside>

      <!-- 右侧主内容区：浅灰底 + 内边距由 .layout-main 提供 -->
      <el-main class="layout-main">
        <!-- 嵌套路由出口：子路由匹配到的页面组件（如 Home.vue）渲染在这里 -->
        <!-- 子路由之间切换时只替换出口内的内容，外壳（顶栏/侧边栏）不会重新渲染 -->
        <router-view />
      </el-main>
    </el-container>

    <!-- AI 助手悬浮入口：放在 .layout-container 直接子层，而不是 header/aside 里面
         原因：那两处都有 backdrop-filter，会把 position:fixed 的后代"关进"它们的坐标系（弹窗跑位的老坑）
         整页版「Ai助手」打开时隐藏它——同一条对话显示两遍还挡内容 -->
    <button v-if="!aiDockHidden" type="button" class="ai-fab" @click="aiDrawerVisible = true">
      <el-icon><ChatDotRound /></el-icon>
      询问助手
    </button>

    <!-- 抽屉式对话面板：append-to-body 同样是为了躲开祖先的 backdrop-filter -->
    <el-drawer
      v-model="aiDrawerVisible"
      class="ai-drawer"
      direction="rtl"
      size="420px"
      append-to-body
      title="AI 智能助手"
    >
      <!-- 头部右侧塞一个清空按钮：与整页版共用 useAiChat().clear，清完两边同时生效 -->
      <template #header>
        <div class="ai-drawer__head">
          <span>AI 智能助手</span>
          <el-button link type="primary" @click="clearAiChat">清空会话</el-button>
        </div>
      </template>
      <ChatPanel />
    </el-drawer>
  </el-container>
</template>

<style scoped>
/* scoped：样式只作用于本组件；要改 Element Plus 内部节点（如菜单项）必须用 :deep() */

/* 外壳撑满视口，高度依赖 global.css 中 html/body/#app 的 100% */
/* position relative + z-index 0：创建堆叠上下文，让背景层压在内容之下、透不出 body */
/* overflow hidden：兜底禁止整页（窗口级）滚动——滚动只允许发生在 el-main 内部 */
.layout-container {
  position: relative;
  z-index: 0;
  height: 100%;
  overflow: hidden;
  /* 后台主体改为浅色资源站风格：淡蓝灰底 + 三处极轻的品牌色光晕 */
  background:
    radial-gradient(1100px 560px at 8% -12%, rgba(79, 110, 247, 0.12), transparent 62%),
    radial-gradient(900px 520px at 100% -6%, rgba(139, 92, 246, 0.09), transparent 58%),
    radial-gradient(800px 600px at 88% 112%, rgba(6, 182, 212, 0.07), transparent 60%),
    var(--color-page-bg);
}

/* 深色粒子背景只属于登录/注册页；后台已改浅色，隐藏这一层避免与白卡冲突 */
.layout-bg {
  display: none;
}

/* 关键修复：flex 子项默认 min-height:auto，长列表会把容器整体撑高 → 整页滚动、侧边栏"断了" */
/* min-height:0 解除这个下限，el-main 自带的 overflow:auto 才能真正接管滚动 */
.layout-body {
  min-height: 0;
}

/* 顶部通栏：白色毛玻璃，滚动时始终压住主内容 */
.layout-header {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--layout-header-height);
  padding: 0 24px;
  background-color: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(18px) saturate(1.2);
  border-bottom: 1px solid rgba(231, 235, 243, 0.9);
  box-shadow: var(--shadow-header);
  z-index: 10;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* logo：白底圆角方块 + 细描边，浅色顶栏上也有明确的图形锚点 */
.brand-logo {
  width: 38px;
  height: 38px;
  padding: 5px;
  background: #fff;
  border-radius: 12px;
  object-fit: contain;
  box-shadow:
    0 0 0 1px var(--color-border),
    0 6px 14px -8px rgba(23, 35, 61, 0.3);
}

/* 品牌名：渐变文字，和主按钮/标题竖条共用一套品牌色 */
.brand-name {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0.2px;
  background: var(--gradient-accent);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

/* 当前页名做成胶囊标签，弱化但一眼能定位 */
.page-title {
  padding: 4px 12px;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-accent);
  background-color: var(--color-accent-soft);
  border-radius: 999px;
}

.header-right {
  display: flex;
  align-items: center;
}

/* 下拉触发区：头像 + 用户名 + 箭头，整体做成可悬停的胶囊 */
.user-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px 4px 4px;
  cursor: pointer;
  outline: none; /* 去掉 el-dropdown 触发元素聚焦时的默认描边，更贴近后台风格 */
  border-radius: 999px;
  transition: var(--transition-base);
}

.user-trigger:hover {
  background-color: #f3f6ff;
}

/* 头像加一圈白边 + 细描边，在浅色顶栏上有"头像卡"的精致感 */
.user-trigger :deep(.el-avatar) {
  border: 2px solid #fff;
  box-shadow: 0 0 0 1px var(--color-border);
}

/* 下拉箭头：小一号、弱化色，避免抢头像视觉 */
.trigger-arrow {
  font-size: 12px;
  color: var(--color-text-muted);
  transition: var(--transition-base);
}

.user-trigger:hover .trigger-arrow {
  color: var(--color-accent);
}

.username {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-secondary);
}

/* 侧边栏：白色半透明 + 毛玻璃，与顶栏同一材质；右侧细描边界定内容区 */
/* overflow-y auto：菜单项多于视口高度时侧栏自己滚，不再牵连整页 */
.layout-aside {
  position: relative;
  overflow-y: auto;
  background-color: var(--color-aside-bg);
  backdrop-filter: blur(18px) saturate(1.2);
  border-right: 1px solid rgba(231, 235, 243, 0.9);
  box-shadow: none;
  z-index: 9;
}

.aside-menu {
  padding: 12px 12px 20px;
  border-right: none;
  background-color: transparent;
}

/* 菜单项是 Element Plus 内部节点，scoped 下必须 :deep() 才能穿透修改 */
.aside-menu :deep(.el-menu-item) {
  position: relative;
  height: 44px;
  margin-bottom: 4px;
  padding: 0 12px;
  line-height: 44px;
  font-size: 14px;
  font-weight: 500;
  border-radius: 10px;
  transition: var(--transition-base);
}

/* 图标：默认弱化，悬停/选中时染成品牌色 */
.aside-menu :deep(.el-menu-item .el-icon) {
  margin-right: 8px;
  font-size: 18px;
  color: #8794aa;
  transition: var(--transition-base);
}

.aside-menu :deep(.el-menu-item:hover) {
  color: #334155;
  background-color: var(--color-aside-bg-hover);
}

.aside-menu :deep(.el-menu-item:hover .el-icon) {
  color: var(--color-accent);
}

/* 选中态：淡紫底 + 品牌字色 + 左侧渐变竖条 */
.aside-menu :deep(.el-menu-item.is-active) {
  font-weight: 600;
  color: var(--color-accent);
  background: var(--gradient-accent-soft);
  box-shadow: inset 0 0 0 1px rgba(79, 110, 247, 0.1);
}

.aside-menu :deep(.el-menu-item.is-active .el-icon) {
  color: var(--color-accent);
}

.aside-menu :deep(.el-menu-item.is-active::before) {
  content: '';
  position: absolute;
  top: 50%;
  left: 0;
  width: 3px;
  height: 20px;
  background: var(--gradient-accent);
  border-radius: 999px;
  transform: translateY(-50%);
}

/* 主内容区：背景由 .layout-container 统一提供，各页面白卡浮在其上 */
.layout-main {
  padding: 20px 24px 28px;
  background-color: transparent;
}

/* AI 悬浮按钮：默认收成圆形图标，避免压住表格操作列/分页；悬停展开成胶囊显示文字 */
/* z-index 低于 EP 抽屉（抽屉会自己分配 2000+） */
.ai-fab {
  position: fixed;
  right: 28px;
  bottom: 28px;
  z-index: 1900;
  display: flex;
  gap: 0;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  padding: 0;
  overflow: hidden;
  font-size: 0;
  font-weight: 600;
  color: #fff;
  white-space: nowrap;
  background: var(--gradient-accent);
  border: none;
  border-radius: 50%;
  box-shadow:
    0 14px 30px -10px rgba(79, 110, 247, 0.6),
    inset 0 1px 0 rgba(255, 255, 255, 0.25);
  cursor: pointer;
  transition: var(--transition-base);
}

.ai-fab .el-icon {
  font-size: 21px;
}

.ai-fab:hover {
  gap: 6px;
  width: 136px;
  padding: 0 18px;
  font-size: 14px;
  border-radius: 26px;
  filter: brightness(1.06);
  box-shadow:
    0 18px 36px -12px rgba(79, 110, 247, 0.7),
    inset 0 1px 0 rgba(255, 255, 255, 0.25);
  transform: translateY(-3px);
}

.ai-fab:active {
  transform: translateY(-1px);
}

.ai-drawer__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
}

/* 抽屉内容区改成纵向不滚动容器：滚动只发生在 ChatPanel 的消息区，输入框固定在底部 */
.ai-drawer :deep(.el-drawer__body) {
  display: flex;
  flex-direction: column;
  padding: 16px;
  overflow: hidden;
}
</style>
