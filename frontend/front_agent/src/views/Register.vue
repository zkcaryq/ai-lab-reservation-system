<script setup>
// 注册页：与登录页共用背景与卡片外壳，只保留"注册"自己的表单逻辑
import { reactive, ref } from 'vue'
// useRouter：注册成功后跳回登录页去登录
import { useRouter } from 'vue-router'
// ElMessage：全局轻提示（顶部成功/失败条）
import { ElMessage } from 'element-plus'
// 局部注册图标：确认密码框复用锁图标
import { Lock, User } from '@element-plus/icons-vue'
// 共享背景：粒子连线 canvas + 光斑（登录页同款）
import AuthBackground from '@/components/AuthBackground.vue'
// 共享卡片外壳：logo + 标题 + 玻璃拟态样式（登录页同款）
import AuthCard from '@/components/AuthCard.vue'
import { registerApi } from '@/api/auth'

const router = useRouter()

// ===== 表单状态与校验 =====
// 表单组件引用：用于手动调用 validate() 触发整体校验
const formRef = ref(null)
// 表单数据对象：比登录多一个 confirmPassword（确认密码）
const form = reactive({
  username: '',
  password: '',
  confirmPassword: '',
})
// 校验规则：前端校验只改善体验，最终校验权在后端接口
const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, message: '用户名至少 3 位', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    // 自定义校验器：validator(rule, value, callback)，callback() 表示通过，callback(new Error(文案)) 表示失败
    // 这里校验"两次密码一致"：异步校验库 async-validator 的写法，Element Plus 表单底层就是它
    {
      validator: (rule, value, callback) => {
        if (value === form.password) {
          callback()
        } else {
          callback(new Error('两次输入的密码不一致'))
        }
      },
      trigger: 'blur',
    },
  ],
}
// 提交按钮 loading 态：请求期间为 true，按钮显示转圈并自动禁用，防止重复提交
const loading = ref(false)

// 点击注册：先校验、再提交
async function handleRegister() {
  // validate() 全部通过才 resolve，任一失败会 reject；这里把失败转成 false，避免未捕获异常
  const valid = await formRef.value.validate().catch(() => false)
  // 校验不通过直接停止，错误文案已由 el-form-item 显示在输入框下方
  if (!valid) return
  // 防重复提交双保险（button 的 :loading 已会禁用，这里防同帧极端连点）
  if (loading.value) return
  loading.value = true
  try {
    // 发起注册请求：失败（非 2xx / 网络异常）时拦截器已弹提示并 reject，控制流直接进 catch
    const res = await registerApi(form)
    // HTTP 200 不代表业务成功：业务码也是 200 才提示成功并跳回登录页（注册不保存登录态）
    if (res.code >= 200 && res.code < 300) {
      ElMessage.success(res.message || '注册成功!')
      // 跳回登录页去登录：push 留下历史记录，浏览器返回可回注册页
      await router.push('/login')
    }
  } catch {
    // 请求层失败的提示已由 request.js 拦截器统一弹出；这里只接住异常防 Uncaught (in promise)，故意留空
  } finally {
    // 无论成功失败都恢复按钮状态（finally 保证执行）
    loading.value = false
  }
}
</script>

<template>
  <!-- 注册页：与登录页一样是独立顶级路由，不套 Layout 外壳 -->
  <div class="auth-page">
    <!-- 共享背景层：粒子 + 光斑 + 渐变 -->
    <AuthBackground />

    <!-- 共享卡片外壳：副标题走 prop，表单与底部文字走默认插槽 -->
    <AuthCard subtitle="创建账号 · 开启智能预约">
      <!-- @submit.prevent：阻止表单默认提交行为（否则输入框里按回车会整页刷新） -->
      <el-form ref="formRef" :model="form" :rules="rules" size="large" @submit.prevent>
        <el-form-item prop="username">
          <!-- :prefix-icon 传组件对象；clearable 提供一键清空小按钮 -->
          <el-input v-model="form.username" :prefix-icon="User" placeholder="用户名" clearable />
        </el-form-item>
        <el-form-item prop="password">
          <!-- show-password：小眼睛切换明文 -->
          <el-input
            v-model="form.password"
            :prefix-icon="Lock"
            type="password"
            placeholder="密码（至少 6 位）"
            show-password
          />
        </el-form-item>
        <el-form-item prop="confirmPassword">
          <!-- 确认密码：回车直接提交，注册页常见习惯 -->
          <el-input
            v-model="form.confirmPassword"
            :prefix-icon="Lock"
            type="password"
            placeholder="确认密码"
            show-password
            @keyup.enter="handleRegister"
          />
        </el-form-item>
        <!-- :loading 期间按钮显示转圈并禁用，配合 handleRegister 里的双保险防重复提交 -->
        <el-button class="auth-button" type="primary" :loading="loading" @click="handleRegister">
          {{ loading ? '注册中...' : '注 册' }}
        </el-button>
      </el-form>

      <!-- 回登录：router-link 声明式导航，渲染成 <a> 但不刷新页面 -->
      <p class="auth-switch">已有账号？<router-link to="/login">返回登录</router-link></p>
    </AuthCard>
  </div>
</template>

<style scoped>
/* 页面壳：与登录页一致；overflow-y:auto + 卡片 margin:auto，矮窗口可滚动 */
.auth-page {
  position: fixed;
  inset: 0;
  display: flex;
  padding: 24px 16px;
  overflow-y: auto;
}
</style>
