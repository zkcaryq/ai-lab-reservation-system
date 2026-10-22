<script setup>
// 认证页（登录/注册）共享卡片外壳：logo + 标题 + 副标题 + 默认插槽（表单与底部文字由父页面提供）
// 抽成组件的原因：两页卡片外观、深色输入框穿透样式完全一致，集中维护改一处生效两页
import logoUrl from '@/assets/imgs/logo-256.png'

// props 声明：subtitle 由父页面传入（登录/注册副标题文案不同）
// defineProps 是 <script setup> 编译宏，无需 import
defineProps({
  subtitle: {
    type: String,
    default: '',
  },
})
</script>

<template>
  <!-- 玻璃拟态卡片：居中交给父级 flex -->
  <div class="auth-card">
    <img class="auth-logo" :src="logoUrl" alt="系统 logo" />
    <h1 class="auth-title">AI 智能实验室预约系统</h1>
    <!-- 副标题走 prop：文案差异由父页面决定，外壳保持统一 -->
    <p class="auth-subtitle">{{ subtitle }}</p>
    <!-- 默认插槽：父页面模板里写在 <AuthCard> 内部的内容（el-form、提示、跳转链接）渲染在这里 -->
    <slot />
  </div>
</template>

<style scoped>
/* 认证卡片：与后台一致的白色大圆角 + 品牌渐变条 + 悬浮阴影 */
.auth-card {
  position: relative;
  z-index: 1;
  width: min(420px, calc(100vw - 32px));
  padding: 44px 40px 30px;
  margin: auto;
  overflow: hidden;
  text-align: center;
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid rgba(255, 255, 255, 0.92);
  border-radius: 22px;
  backdrop-filter: blur(20px) saturate(1.2);
  box-shadow:
    0 32px 80px -36px rgba(30, 41, 89, 0.45),
    0 2px 6px rgba(30, 41, 89, 0.06);
  animation: card-in 0.6s cubic-bezier(0.22, 1, 0.36, 1) both;
}

/* 卡片顶部品牌渐变条：和后台页面标题/主按钮同一视觉语言 */
.auth-card::before {
  content: '';
  position: absolute;
  top: 0;
  right: 36px;
  left: 36px;
  height: 3px;
  background: var(--gradient-accent);
  border-radius: 0 0 999px 999px;
}

@keyframes card-in {
  from {
    opacity: 0;
    transform: translateY(24px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

/* logo 做成 App 图标：白底圆角 + 细描边 + 品牌色阴影 */
.auth-logo {
  width: 68px;
  height: 68px;
  padding: 12px;
  object-fit: contain;
  background: #fff;
  border-radius: 20px;
  box-shadow:
    0 0 0 1px var(--color-border),
    0 16px 32px -18px rgba(79, 110, 247, 0.55);
}

.auth-title {
  margin: 18px 0 8px;
  font-size: 23px;
  font-weight: 800;
  letter-spacing: 0.5px;
  color: var(--color-text-primary);
}

.auth-subtitle {
  margin-bottom: 28px;
  font-size: 13px;
  letter-spacing: 1.5px;
  color: var(--color-text-muted);
}

/* 输入框：浅灰底 + 聚焦品牌环，和后台表单同一套质感 */
.auth-card :deep(.el-input__wrapper) {
  background: rgba(247, 249, 253, 0.92);
  border-radius: 12px;
  box-shadow: 0 0 0 1px var(--color-border) inset;
  transition: var(--transition-base);
}

.auth-card :deep(.el-input__wrapper:hover) {
  background: #fff;
  box-shadow: 0 0 0 1px #c6d2ef inset;
}

.auth-card :deep(.el-input__wrapper.is-focus) {
  background: #fff;
  box-shadow:
    0 0 0 1px var(--color-accent) inset,
    0 0 0 4px rgba(79, 110, 247, 0.12);
}

.auth-card :deep(.el-input__inner) {
  color: var(--color-text-primary);
}

.auth-card :deep(.el-input__inner::placeholder),
.auth-card :deep(.el-input__prefix) {
  color: var(--color-text-muted);
}

/* 渐变主按钮：与后台 primary 按钮同款，但更高更宽，符合登录页的主动作定位 */
.auth-card :deep(.auth-button) {
  width: 100%;
  height: 44px;
  margin-top: 8px;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 4px;
  background: var(--gradient-accent);
  border: none;
  border-radius: 12px;
  box-shadow: 0 12px 26px -12px rgba(79, 110, 247, 0.65);
  transition: var(--transition-base);
}

.auth-card :deep(.auth-button:hover) {
  filter: brightness(1.06);
  transform: translateY(-1px);
  box-shadow: 0 16px 30px -12px rgba(79, 110, 247, 0.7);
}

/* 底部说明文字（插槽内容） */
.auth-card :deep(.auth-tip) {
  margin-top: 16px;
  font-size: 12px;
  color: var(--color-text-muted);
}

/* 登录/注册互跳链接行（插槽内容） */
.auth-card :deep(.auth-switch) {
  margin-top: 14px;
  font-size: 13px;
  color: var(--color-text-secondary);
}

/* 链接本身高亮 + 悬停加深并出现下划线 */
.auth-card :deep(.auth-switch a) {
  font-weight: 600;
  color: var(--color-accent);
}

.auth-card :deep(.auth-switch a:hover) {
  color: #3f58c6;
  text-decoration: underline;
  text-underline-offset: 3px;
}

/* 系统"减少动态效果"时关闭入场动画 */
@media (prefers-reduced-motion: reduce) {
  .auth-card {
    animation: none;
  }
}

@media (max-width: 480px) {
  .auth-card {
    padding: 36px 24px 26px;
  }
}
</style>
