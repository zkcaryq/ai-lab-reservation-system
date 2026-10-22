<script setup>
// 个人信息页（真接口版）：
// ① 挂载时 GET /api/user/info 拉最新资料回填表单
// ② 头像可点击上传（POST /api/files/upload，只写本地副本，保存才落库）
// ③ 保存：无改动拦截 + diff 提交 PATCH /api/user/update（只发变化字段），成功后 updateUser 同步 store 并刷新基线
// ④ 带未保存修改离开页面时，onBeforeRouteLeave 二次确认拦截
import { computed, onMounted, reactive, ref } from 'vue'
// 组件内路由守卫：只在"离开本页面"时触发，用于未保存拦截
import { onBeforeRouteLeave } from 'vue-router'
// 用户接口：获取信息 / 更新信息（封装在 src/api/user.js）
import { getUserInfoApi, updateUserInfoApi } from '@/api/user'
// 文件上传接口：头像图片（封装在 src/api/file.js）
import { uploadFileApi } from '@/api/file'
// 共享登录态 store：保存成功后 updateUser，顶栏等引用 userInfo 的地方立即刷新
import { useUser } from '@/utils/user'
// ElMessage 轻提示；ElMessageBox 确认弹窗（离开时的未保存拦截）
import { ElMessage, ElMessageBox } from 'element-plus'
// 相对路径 → 绝对 URL 工具：后端存的是 /uploads/xxx.png，拼上后端地址浏览器才加载得到
import { resolveBackendUrl } from '@/utils/url'
// 图标：User 是无头像时的兜底；Plus 提示"点击可上传"
// （main.js 已全局注册全部图标，这里显式 import 让本文件依赖一目了然）
import { Plus, User } from '@element-plus/icons-vue'

// 只解构 updateUser：本页展示读 form，不直接读 userInfo，唯一写 store 的时机是保存成功
const { updateUser } = useUser()

// 全页 loading：加载 / 上传 / 保存三个阶段共用，驱动 v-loading 遮罩和保存按钮禁用
const loading = ref(false)

// 本地编辑副本：所有输入只改这里，不碰共享 store
// 保存成功后用后端返回的最新数据 updateUser，保证 store 与数据库一致
const form = reactive({
  username: '',
  name: '',
  role: '',
  email: '',
  phone: '',
  avatar: '',
  // 注册时间：后端 UserResponse.created_at，只读展示；不进 diff 白名单，永不提交
  created_at: '',
})

// 基线快照：加载成功/保存成功后各记一次"原始状态"，是"用户到底改没改"的参照物
// null 表示还没加载完，此时保存/离开一律按"无改动"处理
const original = ref(null)

// 是否有未保存的修改：只比对四个可提交字段（username/role 不可编辑，不参与）
const isDirty = computed(() => {
  if (!original.value) return false
  return (
    form.name !== original.value.name ||
    form.email !== original.value.email ||
    form.phone !== original.value.phone ||
    form.avatar !== original.value.avatar
  )
})

// 把指定来源（form 或后端返回的 data）里的四个可提交字段记为新基线
function takeSnapshot(source) {
  original.value = {
    name: source.name,
    email: source.email,
    phone: source.phone,
    avatar: source.avatar,
  }
}

// 表单组件引用：保存时手动调用 validate() 触发整体校验
const formRef = ref(null)

// 校验规则（教程11的修正版）：required 拼写、手机号 {9} 量词都已纠正
// 前端校验只改善体验，最终校验权在后端接口
const rules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  email: [{ type: 'email', message: '邮箱格式错误', trigger: 'blur' }],
  phone: [
    { pattern: /^1[3-9]\d{9}$/, message: '手机号格式错误（需 11 位大陆手机号）', trigger: 'blur' },
  ],
}

// 角色码 → 中文标签：后端存英文码（admin / student），页面展示中文；角色不可自改
const roleLabel = computed(() => {
  return form.role === 'admin' ? '管理员' : form.role === 'student' ? '学生' : '未知角色'
})

// 头像展示地址：相对路径转绝对 URL；空值返回 ''，el-avatar 视为无图走插槽兜底
const avatarUrl = computed(() => resolveBackendUrl(form.avatar))

// 上传前置校验（el-upload 的闸门钩子）：返回 false 直接中止，不发请求
function beforeAvatarUpload(file) {
  // 白名单校验 MIME 类型，与 accept 属性双保险（accept 只限制选择框，拖拽可绕过）
  const imageTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
  if (!imageTypes.includes(file.type)) {
    ElMessage.error('只能上传 jpg/png/gif/webp 图片')
    return false
  }
  // 字节 → MB，超过 5 拒绝；与后端 settings.MAX_UPLOAD_FILE_BYTES（5 MiB）保持一致
  if (file.size / 1024 / 1024 > 5) {
    ElMessage.error('图片大小不能超过 5MB')
    return false
  }
  return true
}

// 自定义上传：:http-request 会接管 el-upload 的默认 XHR，回调收到 { file }
async function handleFileUpload({ file }) {
  loading.value = true
  try {
    const res = await uploadFileApi(file)
    // 成功判定统一用 2xx 区间（与拦截器 isSuccess 口径一致）
    if (res.code >= 200 && res.code < 300) {
      // 只写进本地副本并提示：上传 ≠ 落库，后端明说 avatar 由资料更新接口写入
      form.avatar = res.data?.url
      ElMessage.warning('头像已上传，点击保存修改生效')
    }
    // 非 2xx：拦截器已弹提示并 reject，控制流进 catch，页面不写 else 防双重提示
  } catch {
    // 网络/HTTP 层失败的提示已由 request.js 拦截器统一弹出，这里只终结异常链，故意留空
  } finally {
    loading.value = false
  }
}

// 保存修改：校验 → 无改动拦截 → diff 提交 → 成功后同步共享 store 并刷新基线
async function handleSave() {
  // validate() 全部通过才 resolve，任一失败转 false 并由表单项显示红字
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  // 无改动拦截：什么都不改反复点保存，不再空发 PATCH 请求
  if (!isDirty.value) {
    ElMessage.info('当前没有未保存的修改')
    return
  }
  // 复用全页 loading：遮罩 + 按钮禁用，防止连点连发 PATCH
  loading.value = true
  try {
    // diff 提交：只发"与基线不同"的字段——天然贴合 PATCH 语义
    // 同时解决空串歧义：'' 只在用户主动清空时才发（有意清空）；
    // 没动的字段不发，后端 exclude_none 跳过，不存在误覆盖风险
    // username/role/status 不在后端 Schema 里，始终不发
    const payload = {}
    if (form.name !== original.value.name) payload.name = form.name
    if (form.email !== original.value.email) payload.email = form.email
    if (form.phone !== original.value.phone) payload.phone = form.phone
    if (form.avatar !== original.value.avatar) payload.avatar = form.avatar
    const res = await updateUserInfoApi(payload)
    // 成功判定统一用 2xx 区间（与拦截器 isSuccess 口径一致）
    if (res.code >= 200 && res.code < 300) {
      // 用后端返回的最新用户对象同步共享 store：顶栏等引用处立即刷新
      updateUser(res.data)
      // 用后端返回值（权威数据）刷新基线：此刻回到"零改动"，再点保存会被拦截
      takeSnapshot(res.data)
      ElMessage.success(res.message || '更新个人信息成功！Ovo!')
    }
    // code!==200：拦截器已弹过提示，不写 else，避免双重提示
  } catch {
    // 网络/HTTP 层失败的提示已由 request.js 拦截器统一弹出，这里只终结异常链，故意留空
  } finally {
    // 无论成功失败都收回 loading：遮罩消失、按钮恢复可点
    loading.value = false
  }
}

// 拉取当前用户信息回填表单：以后端为准（比直接读 localStorage 的登录快照更新）
const loadingUserInfo = async () => {
  loading.value = true
  try {
    const res = await getUserInfoApi()
    // 成功判定统一用 2xx 区间（与拦截器 isSuccess 口径一致）
    if (res.code >= 200 && res.code < 300) {
      // 整体灌入后端返回的用户对象；多带的 id/status/created_at 存进 form 无害——提交走 diff 白名单，不会外泄
      Object.assign(form, res.data)
      // 记基线：之后的 isDirty 判断与 diff 提交都以这份快照为参照
      takeSnapshot(res.data)
    }
    // code!==200：拦截器已弹过提示，这里不写 else，避免双重提示
  } catch {
    // 网络/HTTP 层失败的提示已由 request.js 拦截器统一弹出，这里只终结异常链，故意留空
  } finally {
    loading.value = false
  }
}

// 挂载完成即发起请求：此时模板已渲染，v-loading 遮罩能看到效果
onMounted(() => {
  loadingUserInfo()
})

// 组件内路由守卫（vue-router 的 onBeforeRouteLeave）：只在"离开本页面"时触发
// 侧边栏切换、下拉导航、浏览器返回都会走到这里；有未保存修改就二次确认
// 返回 false 取消本次导航，页面留在原处；基线未就绪（还在加载）视为无改动直接放行
onBeforeRouteLeave(async () => {
  if (!isDirty.value) return true
  try {
    await ElMessageBox.confirm('有未保存的修改，确定要离开吗？', '提示', {
      confirmButtonText: '仍要离开',
      cancelButtonText: '继续编辑',
      type: 'warning',
    })
    return true
  } catch {
    // 点了"继续编辑"或关闭弹窗：取消导航
    return false
  }
})
</script>

<template>
  <!-- 白卡：限宽 640 水平居中；scoped 样式不跨组件，卡片样式本组件自带 -->
  <div class="profile-card">
    <!-- 头部信息带：头像（可点击上传）+ 用户名 + 角色 tag + 邮箱副行 -->
    <header class="profile-head">
      <!-- 上传触发区：普通 div 容器（这里不在 el-form 内，用 el-form-item 只是徒增边距） -->
      <div class="profile-head__upload">
        <!-- el-upload：http-request 接管上传走我们的 api；show-file-list 关掉文件列表；accept 限制选择框 -->
        <el-upload
          class="avatar-uploader"
          :http-request="handleFileUpload"
          :show-file-list="false"
          :before-upload="beforeAvatarUpload"
          accept="image/jpeg,image/png,image/gif,image/webp"
        >
          <!-- 触发区就是头像本身：有图显示图，没图显示 + 号提示可点 -->
          <el-avatar :size="64" class="profile-head__avatar" :src="avatarUrl">
            <el-icon v-if="!form.avatar"><Plus /></el-icon>
            <el-icon v-else><User /></el-icon>
          </el-avatar>
        </el-upload>
      </div>
      <div class="profile-head__meta">
        <div class="profile-head__line">
          <!-- 用户名：后端真实数据 -->
          <span class="profile-head__name">{{ form.username || '未登录' }}</span>
          <!-- 角色 tag：码值翻译后的中文，小号信息标签 -->
          <el-tag size="small" type="info">{{ roleLabel }}</el-tag>
        </div>
        <!-- 邮箱副行：弱化色小字，承担"第二信息层" -->
        <p class="profile-head__sub">{{ form.email || '未设置邮箱' }}</p>
      </div>
    </header>

    <!-- 分隔线：头部信息带与编辑区之间的视觉分组 -->
    <el-divider />

    <!-- 编辑区：:model 绑本地副本，:rules 挂校验，v-loading 覆盖加载/上传/保存三个阶段 -->
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="80px"
      class="profile-form"
      v-loading="loading"
    >
      <el-form-item label="账号" prop="username">
        <!-- 账号由后端签发、不可自改：disabled 只读展示 -->
        <el-input v-model="form.username" disabled placeholder="账号" />
      </el-form-item>
      <el-form-item label="名称" prop="name">
        <!-- 可编辑字段：v-model 绑本地副本，blur 时按 rules 校验 -->
        <!-- maxlength 从源头防超长：再长的字输不进去，也避免撞数据库列宽报 500；show-word-limit 显示计数 -->
        <el-input
          v-model="form.name"
          placeholder="请输入名称"
          clearable
          maxlength="50"
          show-word-limit
        />
      </el-form-item>
      <el-form-item label="角色" prop="role">
        <!-- 角色不可自改：展示 computed 翻译后的中文标签 -->
        <el-input :model-value="roleLabel" disabled placeholder="角色" />
      </el-form-item>
      <el-form-item label="邮箱" prop="email">
        <!-- maxlength 100：邮箱长度的防御性上限 -->
        <el-input v-model="form.email" placeholder="请输入邮箱" clearable maxlength="100" />
      </el-form-item>
      <el-form-item label="手机号" prop="phone">
        <!-- maxlength 11：大陆手机号定长，输多了直接截住，与 pattern 校验互补 -->
        <el-input v-model="form.phone" placeholder="请输入手机号" clearable maxlength="11" />
      </el-form-item>
      <el-form-item label="注册时间">
        <!-- 注册时间：后端已格式化好的时间串，只读直显（单向 :model-value + disabled，与角色同款） -->
        <el-input :model-value="form.created_at" disabled placeholder="注册时间" />
      </el-form-item>
      <!-- 动作行：label-width="0" 取消本行的 80px 标签列偏移，配合下方样式让按钮相对整卡真居中 -->
      <el-form-item label-width="0" class="profile-form__actions">
        <el-button type="primary" :loading="loading" @click="handleSave">保存修改</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<style scoped>
/* 白卡：限宽 640px 并水平居中（margin auto），单卡页的档案卡构图；玻璃化透出粒子 */
.profile-card {
  max-width: 640px;
  margin: 0 auto;
  padding: 24px;
  background-color: var(--color-surface-glass);
  backdrop-filter: blur(12px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}

/* 头部信息带：头像在上、姓名/角色/邮箱居中纵排，经典档案卡视觉 */
.profile-head {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

/* 上传触发区容器：抹掉行内基线缝隙，避免头像下方多出空隙 */
.profile-head__upload {
  line-height: 0;
}

/* 悬停反馈：主色描边提示头像可点击（.el-upload 是 EP 内部节点，scoped 需 :deep 穿透） */
.profile-head__upload :deep(.el-upload) {
  border-radius: 50%;
  cursor: pointer;
  transition: var(--transition-base);
}

.profile-head__upload :deep(.el-upload:hover) {
  box-shadow: 0 0 0 2px var(--color-accent);
}

/* 头像兜底底色：主题软渐变，替代 EP 默认灰圆的"未完成感" */
.profile-head__avatar {
  background: var(--gradient-accent-soft);
  color: var(--color-text-secondary);
  font-size: 24px;
}

.profile-head__line {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 用户名：卡片内最高文字层级 */
.profile-head__name {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
}

/* 邮箱副行：弱化色小字 */
.profile-head__sub {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-muted);
}

/* 表单铺满卡片内容宽：卡片已限宽 640，不再二次限宽 */
.profile-form {
  width: 100%;
}

/* 动作行居中：el-form-item 的 content 本身是 flex 容器，justify-content 让按钮水平居中 */
.profile-form__actions :deep(.el-form-item__content) {
  justify-content: center;
}
</style>
