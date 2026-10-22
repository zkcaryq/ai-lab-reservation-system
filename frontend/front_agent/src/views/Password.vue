<script setup>
// 修改密码页（一次性表单）：无加载、无基线、无脏检查、无离开守卫
// 原因：后端从不返回密码（UserResponse 不含 password），本页没有任何"原始数据"可拉取和比对，
// Profile 那套"加载+diff+守卫"在这里既无意义也不成立。本页只做：校验 → 提交 → 成功清登录态重登
import { computed, reactive, ref } from 'vue'
// 组件内编程式导航：成功后跳登录页
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
// 修改密码接口：PATCH /api/user/password（封装在 api/user.js；method 以后端定盘为准，只改 api 层一行）
import { updatePasswordApi } from '@/api/user'
// 密码已变，本地登录态语义过期：logout 成对清除 token 与用户信息
import { logout } from '@/utils/auth'
// 输入框前缀图标：三框统一用锁；User 是无头像时的兜底图标
import { Lock, User } from '@element-plus/icons-vue'
// 身份展示（头像/昵称/角色）读共享 store：登录态里本来就有这些非敏感字段，
// 不需要也不应该发请求——后端从不返回密码，但 userInfo 足够渲染头部
import { useUser } from '@/utils/user'
import { resolveBackendUrl } from '@/utils/url'

const router = useRouter()

// 顶栏同款数据源：模块级 ref，登录/保存后自动刷新
const { userInfo } = useUser()
// 头像相对路径转绝对 URL；空值走插槽图标兜底
const headerAvatarUrl = computed(() => resolveBackendUrl(userInfo.value?.avatar))
// 角色码 → 中文标签（与 Profile 同口径）
const roleLabel = computed(() => {
  if (userInfo.value?.role === 'admin') return '管理员'
  if (userInfo.value?.role === 'student') return '学生'
  return '未知角色'
})

// 表单组件引用：提交前整体校验
const formRef = ref(null)
// 提交按钮 loading：请求期间转圈并禁用，防重复提交
const submitting = ref(false)

// 表单：字段命名用前端 camelCase；到 api 调用处才翻译成后端 snake_case
const form = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
})

// 校验规则：
// - 原密码：必填（它只被后端验证，不参与强度检查）
// - 新密码：必填 + min 6（与注册口径一致）+ validator 拒绝与原密码相同（提前拦截后端同款 400）
// - 确认密码：必填 + 与新密码交叉一致校验（注册页同款 validator 第三次复用）
const rules = {
  oldPassword: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '新密码至少 6 位', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        // 空值交给 required 报文案，这个 validator 只管"与原密码相同"
        if (value && value === form.oldPassword) {
          callback(new Error('新密码不能与原密码相同'))
        } else {
          callback()
        }
      },
      trigger: 'blur',
    },
  ],
  confirmPassword: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        if (value === form.newPassword) {
          callback()
        } else {
          callback(new Error('两次输入的密码不一致'))
        }
      },
      trigger: 'blur',
    },
  ],
}

// 提交：校验 → 防重 → 字段翻译提交 → 成功清登录态回登录页
async function handleSubmit() {
  // validate() 全部通过才 resolve，任一失败转 false 并由表单项显示红字
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  // 防重复提交双保险（按钮 :loading 已禁用，这里防同帧极端连点）
  if (submitting.value) return
  submitting.value = true
  try {
    // 命名翻译层：camelCase 表单 → snake_case 契约，只发生在这一处
    // confirmPassword 永不提交：它只是浏览器本地的防手滑字段
    const res = await updatePasswordApi({
      old_password: form.oldPassword,
      new_password: form.newPassword,
    })
    // 成功判定统一用 2xx 区间（后端业务码可能是 200/201 等，与拦截器 isSuccess 口径一致）
    if (res.code >= 200 && res.code < 300) {
      ElMessage.success('密码修改成功，请重新登录')
      // 客户端清理登录态；注意：服务端旧 JWT 仍有效到自然过期，这里不是撤销
      logout()
      // await 等导航完成再继续，保证登出与跳转的先后语义
      await router.push('/login')
    }
    // code!==200（如"原密码错误"）：拦截器已弹过后端 message，页面不写 else 防双重提示
  } catch {
    // 网络/HTTP 层失败的提示已由 request.js 拦截器统一弹出，这里只终结异常链，故意留空
  } finally {
    // 无论成功失败都恢复按钮（成功分支会跳走，finally 先执行无碍）
    submitting.value = false
  }
}
</script>

<template>
  <!-- 档案卡同族：640 居中白卡；scoped 样式不跨组件，本组件自带 -->
  <div class="password-card">
    <!-- 头部信息带：真实头像 + 用户名 + 角色 tag + 预期管理副标题（数据全部来自共享 store） -->
    <header class="password-head">
      <!-- 头像：有 URL 显示图片；无头像渲染默认插槽的 User 图标兜底 -->
      <el-avatar :size="64" class="password-head__avatar" :src="headerAvatarUrl || undefined">
        <el-icon><User /></el-icon>
      </el-avatar>
      <div class="password-head__line">
        <span class="password-head__name">{{ userInfo?.name || '未登录' }}</span>
        <el-tag size="small" type="info">{{ roleLabel }}</el-tag>
      </div>
      <h3 class="password-head__title">修改密码</h3>
      <!-- 把"会被登出"写进页面文案：用户提交前就知道后果，不是被踢下线才发现 -->
      <p class="password-head__desc">修改成功后当前登录状态将失效，需使用新密码重新登录</p>
    </header>

    <!-- 分隔线：头部与表单的视觉分组 -->
    <el-divider />

    <!-- 表单：label-width 与 Profile 同规格；@submit.prevent 防回车触发原生提交刷新整页 -->
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="80px"
      class="password-form"
      @submit.prevent
    >
      <el-form-item label="原密码" prop="oldPassword">
        <!-- 密码框三件套：type=password 掩码 + show-password 小眼睛 + Lock 前缀图标 -->
        <!-- 不做 clearable：密码框的 × 容易误触；maxlength 64 防超长（列宽防御） -->
        <el-input
          v-model="form.oldPassword"
          type="password"
          show-password
          :prefix-icon="Lock"
          maxlength="64"
          placeholder="请输入原密码"
        />
      </el-form-item>
      <el-form-item label="新密码" prop="newPassword">
        <el-input
          v-model="form.newPassword"
          type="password"
          show-password
          :prefix-icon="Lock"
          maxlength="64"
          placeholder="至少 6 位，且不与原密码相同"
          @keyup.enter="handleSubmit"
        />
      </el-form-item>
      <el-form-item label="确认密码" prop="confirmPassword">
        <el-input
          v-model="form.confirmPassword"
          type="password"
          show-password
          :prefix-icon="Lock"
          maxlength="64"
          placeholder="请再次输入新密码"
          @keyup.enter="handleSubmit"
        />
      </el-form-item>
      <!-- 动作行：label-width="0" 去掉 80px 标签列偏移，配合下方样式让按钮相对整卡真居中 -->
      <el-form-item label-width="0" class="password-form__actions">
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          {{ submitting ? '提交中...' : '确认修改' }}
        </el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<style scoped>
/* 白卡：与 Profile 档案卡同族的设计令牌；玻璃化透出粒子 */
.password-card {
  max-width: 640px;
  margin: 0 auto;
  padding: 24px;
  background-color: var(--color-surface-glass);
  backdrop-filter: blur(12px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}

/* 头部：头像 + 姓名行 + 标题 + 副标题纵向居中 */
.password-head {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

/* 头像兜底底色：主题软渐变，与 Profile 档案卡同款 */
.password-head__avatar {
  background: var(--gradient-accent-soft);
  color: var(--color-text-secondary);
  font-size: 24px;
}

/* 姓名 + 角色 tag 横排 */
.password-head__line {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 用户名：卡片内最高文字层级 */
.password-head__name {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
}

/* 标题：卡片内最高文字层级 */
.password-head__title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
}

/* 副标题：弱化色小字，承担"会发生什么"的预期管理 */
.password-head__desc {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-muted);
}

/* 表单铺满卡片内容宽 */
.password-form {
  width: 100%;
}

/* 动作行居中：el-form-item 的 content 是 flex 容器，justify-content 让按钮水平居中 */
.password-form__actions :deep(.el-form-item__content) {
  justify-content: center;
}
</style>
