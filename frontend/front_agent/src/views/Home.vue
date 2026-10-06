<template>
  <!-- 子页面组件：被渲染进 Layout.vue 主内容区的 <router-view /> 出口 -->
  <!-- 页面只写"内容"本身：外壳（顶栏/侧边栏/灰底内边距）全部由 Layout 提供 -->
  <!-- 注意：教程里带 aside/header 的整页代码不能直接粘到这里，那部分外壳本项目放在 Layout.vue -->
  <div class="content-box">
    <!-- 页面主标题 -->
    <h3 class="content-title">系统首页</h3>
    <!-- 页面说明文字 -->
    <p class="content-desc">这里是主页面内容，内部卡片自带柔和阴影与圆角。</p>
  </div>
</template>

<style scoped>
/* 页面卡片：颜色/圆角/阴影都引用 global.css 的设计变量，改主题只需改一处 */
.content-box {
  min-height: 100%;
  padding: 24px;
  background-color: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}

.content-title {
  margin-bottom: 8px;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.content-desc {
  font-size: 14px;
  line-height: 1.7;
  color: var(--color-text-muted);
}
</style>
