<script setup>
// useRoute 返回响应式的"当前路由"对象：地址变化时 route.path / route.meta 自动更新，模板随之重新渲染
// useRouter 提供编程式导航：退出登录后 push 到 /login
import { useRoute, useRouter } from 'vue-router'
import { House } from '@element-plus/icons-vue'
// ElMessage 轻提示；ElMessageBox 确认弹窗（退出前的二次确认）
import { ElMessage, ElMessageBox } from 'element-plus'

// 当前路由对象：菜单选中态用 route.path，顶栏页名用 route.meta.title
const route = useRoute()
const router = useRouter()

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
        // Mock 退出：登录态尚未接入（没有 token 可清除），只跳转到登录页
        router.push('/login')
        ElMessage.success('已退出登录（Mock：登录态未接入）')
      })
      .catch(() => {
        // 用户点了取消：什么都不做，但必须 catch 掉 reject
      })
    return
  }
  // 其余菜单项功能未实现：明确提示"开发中"，而不是点击无反应
  ElMessage.info('功能开发中，将在后续章节实现')
}
</script>

<template>
  <!-- el-container 是 Element Plus 的布局容器（flex）：直接子元素含 el-header 时自动纵向排列 -->
  <el-container class="layout-container">
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
      <!-- 右半区：登录用户信息（目前是静态占位，接入登录功能后替换为真实用户数据） -->
      <div class="header-right">
        <!-- el-dropdown：默认插槽放"触发元素"，#dropdown 具名插槽放"菜单内容" -->
        <!-- @command：点击任意菜单项，把该项的 command 值传给回调，一个函数处理所有菜单项 -->
        <el-dropdown @command="handleCommand">
          <!-- 触发区：头像 + 用户名 + 下拉箭头，横向排列样式见 .user-trigger -->
          <div class="user-trigger">
            <el-avatar
              size="small"
              src="https://cube.elemecdn.com/3/7c/3ea6beec64369c2642b92c6726f1epng.png"
            />
            <span class="username">Admin</span>
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
          <el-menu-item index="/manager/labs">
            <!-- 菜单项图标 -->
            <el-icon><House /></el-icon>
            <!-- #title 是具名插槽：放这里的内容成为菜单文字（侧边栏折叠时靠它切换为悬浮提示） -->
            <template #title>实验室管理</template>
          </el-menu-item>
          <el-menu-item index="/manager/equipment">
            <!-- 菜单项图标 -->
            <el-icon><Setting /></el-icon>
            <!-- #title 是具名插槽：放这里的内容成为菜单文字（侧边栏折叠时靠它切换为悬浮提示） -->
            <template #title>设备列表管理</template>
          </el-menu-item>
          <el-menu-item index="/manager/users">
            <!-- 菜单项图标 -->
            <el-icon><User /></el-icon>
            <!-- #title 是具名插槽：放这里的内容成为菜单文字（侧边栏折叠时靠它切换为悬浮提示） -->
            <template #title>用户管理</template>
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
  </el-container>
</template>

<style scoped>
/* scoped：样式只作用于本组件；要改 Element Plus 内部节点（如菜单项）必须用 :deep() */

/* 外壳撑满视口，高度依赖 global.css 中 html/body/#app 的 100% */
.layout-container {
  height: 100%;
}

/* 顶部通栏 */
.layout-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--layout-header-height);
  padding: 0 24px;
  background-color: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  box-shadow: var(--shadow-header);
  z-index: 10;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* logo 图片：固定 32px 见方，object-fit 保证不变形；无背景色，露出图片自身设计 */
.brand-logo {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  object-fit: contain;
}

.brand-name {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.5px;
  color: var(--color-text-primary);
}

.page-title {
  font-size: 14px;
  color: var(--color-text-secondary);
}

.header-right {
  display: flex;
  align-items: center;
}

/* 下拉触发区：头像 + 用户名 + 箭头横向居中；cursor 放在触发区而不是整块右侧 */
.user-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  outline: none; /* 去掉 el-dropdown 触发元素聚焦时的默认描边，更贴近后台风格 */
}

/* 下拉箭头：小一号、弱化色，避免抢头像视觉 */
.trigger-arrow {
  font-size: 12px;
  color: var(--color-text-muted);
}

.username {
  font-size: 14px;
  color: var(--color-text-secondary);
}

/* 侧边栏 */
.layout-aside {
  background-color: var(--color-aside-bg);
  box-shadow: 2px 0 8px rgba(0, 21, 41, 0.15);
  z-index: 9;
}

.aside-menu {
  padding: 8px;
  border-right: none;
}

/* 菜单项是 Element Plus 内部节点，scoped 下必须 :deep() 才能穿透修改 */
.aside-menu :deep(.el-menu-item) {
  margin-bottom: 4px;
  border-radius: 8px;
  transition: var(--transition-base);
}

.aside-menu :deep(.el-menu-item:hover) {
  background-color: var(--color-aside-bg-hover);
}

.aside-menu :deep(.el-menu-item.is-active) {
  background: var(--gradient-accent-soft);
  font-weight: 500;
}

/* 主内容区 */
.layout-main {
  padding: 16px;
  background-color: var(--color-page-bg);
}
</style>
