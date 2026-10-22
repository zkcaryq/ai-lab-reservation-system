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
// 登录接口函数：url / method 在 api/auth.js 里集中封装，页面只传表单数据
import { loginApi } from '@/api/auth'
// 登录成功后要把 token 与用户信息写入本地：saveLoginData 由 useUser 提供
import { useUser } from '@/utils/user'

const router = useRouter()
// 只解构 saveLoginData：本页不读 userInfo（顶栏显示是 Layout 的职责）
const { saveLoginData } = useUser()

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
    // 发起登录请求：失败（非 2xx / 网络异常）时拦截器已弹提示并 reject，控制流直接进 catch
    const res = await loginApi(form)
    // HTTP 200 不代表业务成功：业务码也是 200 才保存登录态并跳转
    if (res.code >= 200 && res.code < 300) {
      saveLoginData(res.data) // 保存登录态（token、用户信息等）到本地
      ElMessage.success(res.message || '登录成功!')
      // 跳转管理端首页：push 留下历史记录，浏览器返回可回登录页
      await router.push('/manager/home')
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
      <!-- 去注册：router-link 声明式导航，渲染成 <a> 但不刷新页面 -->
      <p class="auth-switch">还没有账号？<router-link to="/register">立即注册</router-link></p>
    </AuthCard>
  </div>
</template>

<style scoped>
/* 页面壳：fixed + inset:0 铺满视口（不用 100vh：视口尺寸变化后 vh 偶发不刷新）
   overflow-y:auto + 卡片 margin:auto：窗口较矮时可滚动，不会裁掉卡片顶部 */
.auth-page {
  position: fixed;
  inset: 0;
  display: flex;
  padding: 24px 16px;
  overflow-y: auto;
}
</style>
