<script setup>
// 登录页：只保留"登录"自己的逻辑（表单 + 校验 + 提交），背景与卡片外壳已抽成共享组件
import { reactive, ref } from 'vue'
// useRouter：编程式导航，登录成功后跳转管理端
import { useRouter } from 'vue-router'
// ElMessage：全局轻提示（顶部成功/失败条）
import { ElMessage } from 'element-plus'
// 局部注册图标：与 main.js 的全量全局注册不同，这里只 import 本页用到的（教程风格，利于 tree-shaking）
import { Lock, User } from '@element-plus/icons-vue'
// 共享背景：粒子连线 canvas + 光斑（注册页同款）
import AuthBackground from '@/components/AuthBackground.vue'
// 共享卡片外壳：logo + 标题 + 玻璃拟态样式（注册页同款）
import AuthCard from '@/components/AuthCard.vue'
import { loginApi } from '@/api/auth.js'

const router = useRouter()

// ===== 表单状态与校验 =====
// 表单组件引用：用于手动调用 validate() 触发整体校验
const formRef = ref(null)
// 表单数据对象：reactive 让其属性具备响应式，模板里 v-model 双向绑定自动收集输入
const form = reactive({
  username: '',
  password: '',
})
// 校验规则：前端校验只改善体验，最终校验权在后端接口
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
}
// 提交按钮 loading 态：请求期间为 true，按钮显示转圈并自动禁用，防止重复提交
const loading = ref(false)

// 点击登录：先校验、再提交
async function handleLogin() {
  // validate() 全部通过才 resolve，任一失败会 reject；这里把失败转成 false，避免未捕获异常
  const valid = await formRef.value.validate().catch(() => false)
  // 校验不通过直接停止，错误文案已由 el-form-item 显示在输入框下方
  if (!valid) return
  // 防重复提交双保险（button 的 :loading 已会禁用，这里防同帧极端连点）
  if (loading.value) return
  loading.value = true
  try {
    const res = await loginApi(form)
    ElMessage.success('登录成功')
    // 跳转管理端首页；router.push 会留下历史记录，浏览器返回可回到登录页
    router.push('/manager/home')
  } finally {
    // 无论成功失败都恢复按钮状态（finally 保证执行）
    loading.value = false
  }
}
</script>

<template>
  <!-- 登录页：独立顶级路由，不套 Layout 外壳（未登录不应看到顶栏/侧边栏） -->
  <div class="auth-page">
    <!-- 共享背景层：粒子 + 光斑 + 渐变 -->
    <AuthBackground />

    <!-- 共享卡片外壳：副标题走 prop，表单与底部文字走默认插槽 -->
    <AuthCard subtitle="实验室资源一览 · 预约一步到位">
      <!-- @submit.prevent：阻止表单默认提交行为（否则输入框里按回车会整页刷新） -->
      <el-form ref="formRef" :model="form" :rules="rules" size="large" @submit.prevent>
        <el-form-item prop="username">
          <!-- :prefix-icon 传组件对象；clearable 提供一键清空小按钮 -->
          <el-input v-model="form.username" :prefix-icon="User" placeholder="用户名" clearable />
        </el-form-item>
        <el-form-item prop="password">
          <!-- show-password：小眼睛切换明文；@keyup.enter 回车提交，登录页常见习惯 -->
          <el-input
            v-model="form.password"
            :prefix-icon="Lock"
            type="password"
            placeholder="密码"
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>
        <!-- :loading 期间按钮显示转圈并禁用，配合 handleLogin 里的双保险防重复提交 -->
        <el-button class="auth-button" type="primary" :loading="loading" @click="handleLogin">
          {{ loading ? '登录中...' : '登 录' }}
        </el-button>
      </el-form>

      <!-- 明确标注 Mock 性质，避免误认为真实后端结果 -->
      <p class="auth-tip">Mock 演示：任意用户名 + 6 位以上密码即可登录</p>
      <!-- 去注册：router-link 声明式导航，渲染成 <a> 但不刷新页面 -->
      <p class="auth-switch">还没有账号？<router-link to="/register">立即注册</router-link></p>
    </AuthCard>
  </div>
</template>

<style scoped>
/* 页面壳：fixed + inset:0 铺满视口（不用 100vh：视口尺寸变化后 vh 偶发不刷新），flex 负责卡片居中 */
.auth-page {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
</style>
