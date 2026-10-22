<script setup>
// 用户管理页（CRUD 完整版）：列表 + 双模式弹窗（新增/编辑）+ 删除确认，前后端已接通；头像支持点击看大图
// TODO（仅剩一条）：Layout「用户管理」菜单项加 v-if="userInfo?.role === 'admin'"（学生藏入口）
import { computed, onMounted, reactive, ref } from 'vue'
// 头像相对路径（/uploads/xxx）转绝对 URL：与 Profile/顶栏同一工具，模板里已接好
import { resolveBackendUrl } from '@/utils/url'
// ElMessage 成功/失败轻提示；ElMessageBox 删除前二次确认——两个都在 element-plus
import { ElMessage, ElMessageBox } from 'element-plus'
// User 图标：无头像时 el-avatar 默认插槽的兜底
// Plus/Search：工具栏按钮图标（main.js 虽全局注册，显式 import 让依赖一目了然）
import { Plus, Search, User } from '@element-plus/icons-vue'
// CRUD 四接口：列表 / 新增 / 修改 / 删除（封装在 api/user.js）
import { createUserApi, deleteUserApi, getUserPageListApi, updateUserApi } from '@/api/user'

// ===== 列表区 =====
// 查询参数：一个 reactive 三处共用（搜索框、分页器、load），避免多份状态各漂各的
const params = reactive({
  page: 1, // 当前页码：搜索时要重置回 1
  pageSize: 10, // 每页条数：提交后端时翻译成 page_size
  keywords: '', // 模糊搜索词：后端按 username/name 匹配
})

// 列表页三态：数据、总数、加载中
const tableData = ref([]) // 当前页行数据
const total = ref(0) // 后端统计的总条数，分页器据此算页数
const loading = ref(false) // 列表请求中标记，驱动表格区 v-loading 遮罩

// 加载当前页数据：挂载 / 换页 / 搜索 / 增删改成功后都汇到这里重拉
async function load() {
  loading.value = true
  try {
    const res = await getUserPageListApi({
      page: params.page,
      // 字段翻译点：前端 camelCase → 查询串 snake_case
      page_size: params.pageSize,
      keywords: params.keywords,
    })
    // 成功判定统一 2xx 区间（与拦截器口径一致）
    if (res.code >= 200 && res.code < 300) {
      // ?? [] 兜底：后端空列表可能给 null，el-table 的 :data 必须是数组
      tableData.value = res.data?.list ?? []
      total.value = res.data?.total ?? 0
    }
    // 非 2xx：拦截器已弹提示并 reject，控制流进 catch
  } catch {
    // 网络/HTTP 层失败的提示已由 request.js 拦截器统一弹出，这里只终结异常链，故意留空
  } finally {
    loading.value = false
  }
}

// 搜索：结果集变了必须回第 1 页——停在第 5 页搜小结果集会看到空表，误判"搜索坏了"
function handleSearch() {
  params.page = 1
  load()
}

// 挂载即拉第一页
onMounted(() => {
  load()
})

// ===== 弹窗区（新增/编辑共用一份表单） =====
// 弹窗开关：el-dialog v-model 绑定
const dialogVisible = ref(false)
// 弹窗提交 loading：与列表 loading 分开——两个区域互不干扰（教程绑错成列表 loading 的坑不跟）
const formLoading = ref(false)
// 弹窗表单引用：保存前单独校验这份表单（和列表页没有 formRef 冲突）
const dialogFormRef = ref(null)

// 弹窗表单：id 有无 = 编辑/新增两种模式的唯一判别依据
// password 只在新增时渲染与校验（编辑接口不收密码——填了也不生效，渲染出来纯属误导）
const form = reactive({
  id: null,
  username: '',
  password: '',
  name: '',
  role: 'student', // 默认学生：新增的大多数场景
  email: '',
  phone: '',
  avatar: '',
  status: 1, // 默认正常
})

// 校验规则用 computed：随 form.id 切换——编辑模式下 password 规则清空
// （若规则不跟着关：字段没渲染但 required 还在，validate 永远过不去）
const dialogRules = computed(() => ({
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: form.id
    ? []
    : [
        { required: true, message: '请输入密码', trigger: 'blur' },
        { min: 3, max: 20, message: '密码 3-20 位', trigger: 'blur' },
      ],
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  email: [{ type: 'email', message: '邮箱格式错误', trigger: 'blur' }],
  phone: [{ pattern: /^1[3-9]\d{9}$/, message: '手机号格式错误', trigger: 'blur' }],
}))

// 重置表单：每次打开弹窗的第一步——杜绝上一条记录的残留污染本次
// （教程原型 resetForm 漏了 password，编辑时手输的密码会悄悄跟着下一次"新增"提交）
function resetForm() {
  Object.assign(form, {
    id: null,
    username: '',
    password: '',
    name: '',
    role: 'student',
    email: '',
    phone: '',
    avatar: '',
    status: 1,
  })
  // 清掉上一次校验残留的红字；弹窗内容懒渲染，首次打开时 ref 还是 null，?. 防身
  dialogFormRef.value?.clearValidate()
}

// 新增：重置出空白表单 → 开弹窗（id=null 即"新增模式"）
function handleCreate() {
  resetForm()
  dialogVisible.value = true
}

// 编辑：先重置再灌入行数据（id 也要带上——它是模式判别与 PUT/DELETE 路径的来源）
function handleEdit(row) {
  resetForm()
  Object.assign(form, {
    id: row.id,
    username: row.username,
    name: row.name,
    role: row.role,
    // ?? '' 兜底：后端可空字段给 null 时，v-model 绑 null 会让输入框行为怪异
    email: row.email ?? '',
    phone: row.phone ?? '',
    avatar: row.avatar ?? '',
    status: row.status,
  })
  dialogVisible.value = true
}

// 保存：校验 → 按 form.id 分流 create/update → 成功关弹窗重拉列表
async function handleSave() {
  const valid = await dialogFormRef.value.validate().catch(() => false)
  if (!valid) return
  formLoading.value = true
  try {
    // 分流：编辑走 PATCH 且只传可改字段白名单（不回传 username/password/id）；新增整包就是载荷
    const res = form.id
      ? await updateUserApi(form.id, {
          name: form.name,
          role: form.role,
          email: form.email,
          phone: form.phone,
          avatar: form.avatar,
          status: form.status,
        })
      : await createUserApi(form)
    // 2xx 判定：后端新增返回 HTTP 201 + JSON code 201，区间判断正好覆盖（=== 200 会误判失败）
    if (res.code >= 200 && res.code < 300) {
      dialogVisible.value = false
      ElMessage.success(res.message || (form.id ? '修改成功!' : '新增成功!'))
      load() // 重拉列表：服务端是数据唯一权威，不做本地改数组
    }
  } catch {
    // 网络/HTTP 层失败的提示已由 request.js 拦截器统一弹出，这里只终结异常链，故意留空
  } finally {
    formLoading.value = false
  }
}

// 删除：二次确认 → 接口 → 页码回退防越界 → 重拉
async function handleDelete(row) {
  // confirm 点"取消"是 reject：catch 转 false 接住，否则就是 Uncaught (in promise)
  const ok = await ElMessageBox.confirm(`确认删除用户 [${row.username}]？`, '确认删除', {
    type: 'warning',
  }).catch(() => false)
  if (!ok) return
  try {
    const res = await deleteUserApi(row.id)
    if (res.code >= 200 && res.code < 300) {
      // 删掉本页最后一条时回退一页：否则停在越界页看到空表，误以为"删除把列表删坏了"
      if (tableData.value.length === 1 && params.page > 1) {
        params.page -= 1
      }
      ElMessage.success(res.message || '删除成功！')
      load()
    }
  } catch {
    // 失败提示已由拦截器统一弹出（如"不能删除当前登录的账号"），这里只终结异常链
  }
}
</script>

<template>
  <!-- 白卡：列表页信息密度高，用全宽卡（与 Profile/Password 的 640 限宽档案卡相反，按内容形态选） -->
  <div class="users-card">
    <!-- 页面主标题 -->
    <h3 class="users-title">用户管理</h3>

    <!-- 搜索栏：输入框定宽 + 查询 + 新增；回车与清空都即时触发查询 -->
    <div class="users-toolbar">
      <el-input
        v-model="params.keywords"
        placeholder="搜索账号或名称"
        clearable
        class="users-toolbar__input"
        @keyup.enter="handleSearch"
        @clear="handleSearch"
      />
      <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
      <!-- 新增入口：success 绿与查询蓝区分"读/写"两种动作气质 -->
      <el-button type="success" :icon="Plus" @click="handleCreate">新增</el-button>
    </div>

    <!-- 表格：:data 绑当前页数据；v-loading 只罩表格区（工具栏保持可操作） -->
    <el-table v-loading="loading" :data="tableData" style="width: 100%">
      <el-table-column prop="username" label="账号" />
      <el-table-column prop="name" label="名称" />
      <el-table-column label="头像" width="90">
        <!-- 具名插槽解构行数据：#default="{ row }"；相对路径过 resolveBackendUrl 才不裂图 -->
        <template #default="{ row }">
          <!-- 有头像：el-image + preview-src-list → 点缩略图弹出全屏大图查看器
               preview-teleported 把查看器挂到 body，否则会被表格的 overflow 裁掉一半 -->
          <el-image
            v-if="row.avatar"
            :src="resolveBackendUrl(row.avatar)"
            :preview-src-list="[resolveBackendUrl(row.avatar)]"
            preview-teleported
            fit="cover"
            class="users-avatar"
          />
          <!-- 无头像：兜底占位图标保持圆形同尺寸；不给它预览列表，点不动的图比没图更误导 -->
          <el-avatar v-else :size="44">
            <el-icon><User /></el-icon>
          </el-avatar>
        </template>
      </el-table-column>
      <el-table-column prop="email" label="邮箱" />
      <el-table-column prop="phone" label="手机号" />
      <el-table-column label="注册时间" width="150">
        <!-- created_at：后端 UserResponse 时间字段，直显原值（2026-10-08 定） -->
        <template #default="{ row }">{{ row.created_at }}</template>
      </el-table-column>
      <el-table-column label="角色" width="100">
        <!-- 码值翻译：与 Profile/Password 的 roleLabel 同模式，表格行内用三元 -->
        <template #default="{ row }">{{ row.role === 'admin' ? '管理员' : '学生' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <!-- el-tag 语义色：success 正常 / danger 禁用（EP 合法值是 danger，教程写的 error 不生效） -->
        <template #default="{ row }">
          <el-tag :type="row.status === 1 ? 'success' : 'danger'">
            {{ row.status === 1 ? '正常' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <!-- 操作列：text bg 轻量按钮，编辑蓝/删除红按"改/毁"的危险等级配色；
           170px + nowrap 与 Lab.vue 同款，防止两个按钮挤成上下两行 -->
      <el-table-column label="操作" width="170" class-name="users-actions">
        <template #default="{ row }">
          <el-button type="primary" text bg @click="handleEdit(row)">编辑</el-button>
          <el-button type="danger" text bg @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页：v-model 双向绑页码与条数；换页即重拉，改条数走 handleSearch 回第 1 页 -->
    <div class="users-pager">
      <el-pagination
        v-model:current-page="params.page"
        v-model:page-size="params.pageSize"
        :total="total"
        :page-sizes="[10, 20, 50]"
        background
        layout="total, sizes, prev, pager, next"
        @current-change="load"
        @size-change="handleSearch"
      />
    </div>
  </div>

  <!-- 新增/编辑共用弹窗：title 随 form.id 切换；width 必须带单位（教程的 "450" 是非法 CSS） -->
  <!-- append-to-body：卡片的 backdrop-filter 会劫持 position:fixed，弹窗必须挂到 body 才按视口定位 -->
  <el-dialog v-model="dialogVisible" :title="form.id ? '编辑用户' : '新增用户'" width="450px" append-to-body>
    <!-- 弹窗内独立表单：ref/rules 都是弹窗自己的，与列表区互不干扰 -->
    <el-form
      ref="dialogFormRef"
      :model="form"
      :rules="dialogRules"
      label-width="80px"
      v-loading="formLoading"
      @submit.prevent
    >
      <el-form-item label="账号" prop="username">
        <!-- 账号创建后不可改：编辑模式 disabled（判别式 !!form.id：null/'' 都算假 → 新增时可填） -->
        <el-input
          v-model="form.username"
          :disabled="!!form.id"
          placeholder="请输入账号"
          maxlength="30"
        />
      </el-form-item>
      <!-- 密码只在新增渲染：编辑接口不收密码，出现即欺骗（v-if 连校验规则一起在 computed 里关了） -->
      <el-form-item v-if="!form.id" label="密码" prop="password">
        <el-input
          v-model="form.password"
          type="password"
          show-password
          placeholder="请输入初始密码"
          maxlength="20"
        />
      </el-form-item>
      <el-form-item label="名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入名称" maxlength="50" />
      </el-form-item>
      <el-form-item label="角色" prop="role">
        <!-- el-select 绑字符串值：option 的 value 与后端 role 码一致 -->
        <el-select v-model="form.role">
          <el-option label="学生" value="student" />
          <el-option label="管理员" value="admin" />
        </el-select>
      </el-form-item>
      <el-form-item label="邮箱" prop="email">
        <el-input v-model="form.email" placeholder="请输入邮箱" maxlength="100" />
      </el-form-item>
      <el-form-item label="手机号" prop="phone">
        <el-input v-model="form.phone" placeholder="请输入手机号" maxlength="11" />
      </el-form-item>
      <el-form-item label="状态" prop="status">
        <!-- :value 绑数字 1/0：与后端 status 列类型一致（EP 2.6+ 用 value 而非 label 传值） -->
        <el-radio-group v-model="form.status">
          <el-radio :value="1">正常</el-radio>
          <el-radio :value="0">禁用</el-radio>
        </el-radio-group>
      </el-form-item>
    </el-form>
    <!-- footer 具名插槽：取消只关弹窗（表单下次打开会 reset，不必清理）；确定走 TODO 桩 -->
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="formLoading" @click="handleSave">确定</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
/* 白卡：manager 子页面族同款令牌；列表页不限宽，信息密度优先；玻璃化透出粒子 */
.users-card {
  padding: 24px;
  background-color: var(--color-surface-glass);
  backdrop-filter: blur(12px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}

.users-title {
  margin: 0 0 16px;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
}

/* 搜索栏：输入框定宽 + 按钮并排，与表格留呼吸距 */
.users-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.users-toolbar__input {
  width: 240px;
}

/* 表格透明化：行背景交给卡片玻璃，表头保留淡灰维持层次（EP 组件 CSS 变量，:deep 穿透） */
.users-card :deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(245, 247, 250, 0.7);
}

/* 头像缩略图：尺寸/圆角与原 el-avatar 观感一致，换成 el-image 后才能点出大图 */
.users-avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: block;
}

/* 操作列禁止换行：与 Lab.vue 同款双保险 */
.users-card :deep(.users-actions .cell) {
  white-space: nowrap;
}

/* 分页右对齐：表格在上方铺满，操作收尾在右下，符合阅读顺序 */
.users-pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
