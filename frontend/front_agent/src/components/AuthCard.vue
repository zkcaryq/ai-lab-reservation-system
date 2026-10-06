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
/* 玻璃拟态卡片：半透明 + 背景模糊 + 入场动画 */
.auth-card {
  position: relative;
  z-index: 1;
  width: 400px;
  padding: 40px 36px 28px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.16);
  backdrop-filter: blur(14px);
  box-shadow: 0 24px 60px -20px rgba(0, 0, 0, 0.55);
  text-align: center;
  animation: card-in 0.6s cubic-bezier(0.22, 1, 0.36, 1) both;
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

.auth-logo {
  width: 56px;
  height: 56px;
  object-fit: contain;
}

.auth-title {
  margin: 12px 0 6px;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 1px;
  color: #ffffff;
}

.auth-subtitle {
  margin-bottom: 28px;
  font-size: 13px;
  letter-spacing: 2px;
  color: rgba(255, 255, 255, 0.55);
}

/* 深色输入框：穿透 Element Plus 内部节点改背景/文字色 */
/* 插槽内容在 DOM 上是 .auth-card 的后代，:deep() 同样能覆盖到 */
.auth-card :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  box-shadow: none;
  transition: var(--transition-base);
}

.auth-card :deep(.el-input__wrapper:hover),
.auth-card :deep(.el-input__wrapper.is-focus) {
  background: rgba(255, 255, 255, 0.1);
  box-shadow: 0 0 0 1px rgba(121, 187, 255, 0.6);
}

.auth-card :deep(.el-input__inner) {
  color: #ffffff;
}

.auth-card :deep(.el-input__inner::placeholder),
.auth-card :deep(.el-input__prefix) {
  color: rgba(255, 255, 255, 0.45);
}

/* 渐变主按钮 + 悬停微抬升（按钮在插槽里，同样靠 :deep 覆盖） */
.auth-card :deep(.auth-button) {
  width: 100%;
  margin-top: 8px;
  border: none;
  border-radius: 10px;
  background: var(--gradient-accent);
  box-shadow: var(--shadow-accent);
  font-size: 15px;
  letter-spacing: 4px;
  transition: var(--transition-base);
}

.auth-card :deep(.auth-button:hover) {
  transform: translateY(-1px);
  filter: brightness(1.08);
}

/* 底部 Mock 说明文字（插槽内容） */
.auth-card :deep(.auth-tip) {
  margin-top: 16px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
}

/* 登录/注册互跳链接行（插槽内容） */
.auth-card :deep(.auth-switch) {
  margin-top: 10px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.55);
}

/* 链接本身高亮 + 悬停加亮 */
.auth-card :deep(.auth-switch a) {
  color: #79bbff;
  font-weight: 500;
}

.auth-card :deep(.auth-switch a:hover) {
  color: #a0cfff;
}

/* 系统"减少动态效果"时关闭入场动画 */
@media (prefers-reduced-motion: reduce) {
  .auth-card {
    animation: none;
  }
}
</style>
