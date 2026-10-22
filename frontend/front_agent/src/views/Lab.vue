<script setup>
// 实验室管理页（CRUD 完整版）：列表 + 双模式弹窗（新增/编辑）+ 封面上传 + 删除确认
// 接线状态：load/create/update/delete/upload 全部已接通；封面缩略图支持点击看大图
// TODO（仅剩一条）：Layout「实验室管理」「用户管理」菜单项加 v-if="userInfo?.role === 'admin'"
import { onMounted, reactive, ref } from 'vue'
// 图片相对路径（/uploads/xxx）转绝对 URL：表格缩略图、弹窗预览、大图都要过它
import { resolveBackendUrl } from '@/utils/url'
// ElMessage 轻提示；ElMessageBox 删除前二次确认
import { ElMessage, ElMessageBox } from 'element-plus'
// Plus/Search：工具栏与上传占位图标
import { Plus, Search } from '@element-plus/icons-vue'
// 实验室 CRUD 四接口（封装在 api/lab.js）
import { createLabApi, deleteLabApi, getLabPageListApi, updateLabApi } from '@/api/lab'
// 封面上传复用文件接口（与头像同一个后端端点）
import { uploadFileApi } from '@/api/file'

// ===== 列表区 =====
// 查询参数：搜索框 / 分页器 / load 三处共用同一对象
const params = reactive({
  page: 1, // 当前页码：搜索时重置回 1
  pageSize: 10, // 每页条数：提交时翻译成 page_size
  keywords: '', // 模糊搜索词：后端按 name/location 匹配
})

// 列表页三态
const tableData = ref([]) // 当前页行数据
const total = ref(0) // 总条数（后端统计）
const loading = ref(false) // 表格区 v-loading 遮罩

// 加载当前页：挂载 / 换页 / 搜索 / 增删改成功后都汇到这里重拉
async function load() {
  loading.value = true
  try {
    const res = await getLabPageListApi({
      page: params.page,
      // 字段翻译点：前端 camelCase → 查询串 snake_case
      page_size: params.pageSize,
      keywords: params.keywords,
    })
    // 成功判定统一 2xx 区间（后端 create 回 201，=== 200 会误判）
    if (res.code >= 200 && res.code < 300) {
      // ?? [] 兜底：el-table 的 :data 必须是数组
      tableData.value = res.data?.list ?? []
      total.value = res.data?.total ?? 0
    }
  } catch {
    // 网络/HTTP 层失败的提示已由 request.js 拦截器统一弹出，这里只终结异常链，故意留空
  } finally {
    loading.value = false
  }
}

// 搜索：结果集变了必须回第 1 页
function handleSearch() {
  params.page = 1
  load()
}

// 挂载即拉第一页
onMounted(() => {
  load()
})

// ===== 弹窗区（新增/编辑共用一份表单） =====
const dialogVisible = ref(false) // 弹窗开关
const formLoading = ref(false) // 弹窗提交/上传 loading（与列表 loading 分开，各罩各的区域）
const dialogFormRef = ref(null) // 弹窗表单引用

// 弹窗表单：字段命名用前端 camelCase；提交时翻译成后端 snake_case（见 buildLabPayload）
// id 有无 = 编辑/新增模式开关
const form = reactive({
  id: null,
  name: '',
  location: '',
  capacity: 20, // 默认 20 人；el-input-number 的 min/max 保证有值
  open_time: '08:00', // 字符串 HH:mm：time-picker 的 value-format 保证
  close_time: '18:00',
  description: '',
  img: '', // 封面：上传成功写入相对路径 /uploads/xxx
  status: 1, // 1 开启 / 0 关闭
})

// 校验规则：name 必填（后端 String(50) 列，maxlength 已在输入框源头限长）
// capacity 由 el-input-number 锁死 1-500 永远有值，required 规则保留只为语义完整
const dialogRules = {
  name: [{ required: true, message: '请输入实验室名称', trigger: 'blur' }],
}

// 载荷翻译器：camelCase 表单 → snake_case 契约，create/update 共用一份逻辑
// （教训：上一版 create 直接发 form，openTime/closeTime 后端不认识，开放时间静默丢失）
function buildLabPayload() {
  return {
    name: form.name,
    location: form.location,
    capacity: form.capacity,
    open_time: form.open_time,
    close_time: form.close_time,
    description: form.description,
    img: form.img,
    status: form.status,
  }
}

// 重置：每次打开弹窗第一步，杜绝上一条残留；顺带清校验红字
function resetForm() {
  Object.assign(form, {
    id: null,
    name: '',
    location: '',
    capacity: 20,
    open_time: '08:00',
    close_time: '18:00',
    description: '',
    img: '',
    status: 1,
  })
  dialogFormRef.value?.clearValidate()
}

// 新增：重置 → 开弹窗
function handleCreate() {
  resetForm()
  dialogVisible.value = true
}

// 编辑：重置 → 灌行数据（snake_case 响应 → camelCase 表单；可空字段 ?? '' 兜底）
function handleEdit(row) {
  resetForm()
  Object.assign(form, {
    id: row.id,
    name: row.name,
    location: row.location ?? '',
    capacity: row.capacity ?? 20,
    open_time: row.open_time ?? '08:00',
    close_time: row.close_time ?? '18:00',
    description: row.description ?? '',
    img: row.img ?? '',
    status: row.status,
  })
  dialogVisible.value = true
}

// 上传前置校验：类型白名单 + 5MB 上限（与后端 MAX_UPLOAD_FILE_BYTES 一致）
function beforeCoverUpload(file) {
  const imageTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
  if (!imageTypes.includes(file.type)) {
    ElMessage.error('只能上传 jpg/png/gif/webp 图片')
    return false
  }
  if (file.size / 1024 / 1024 > 5) {
    ElMessage.error('图片大小不能超过 5MB')
    return false
  }
  return true
}

// 封面上传：http-request 接管默认 XHR；罩的是弹窗（formLoading），不是列表
async function handleFileUpload({ file }) {
  formLoading.value = true
  try {
    const res = await uploadFileApi(file)
    if (res.code >= 200 && res.code < 300) {
      // 只写本地副本：上传 ≠ 落库，点确定保存才写入实验室记录
      form.img = res.data?.url
      ElMessage.warning('封面已上传，点击确定保存后生效')
    }
  } catch {
    // 失败提示已由拦截器统一弹出，这里只终结异常链
  } finally {
    formLoading.value = false
  }
}

// 保存：校验 → 按 id 分流 create/update（载荷统一走 buildLabPayload 翻译）→ 成功关弹窗重拉
async function handleSave() {
  const valid = await dialogFormRef.value.validate().catch(() => false)
  if (!valid) return
  formLoading.value = true
  try {
    const res = form.id
      ? await updateLabApi(form.id, buildLabPayload())
      : await createLabApi(buildLabPayload()) // 新增同样走翻译载荷，绝不整包直发 form
    if (res.code >= 200 && res.code < 300) {
      dialogVisible.value = false
      ElMessage.success(res.message || (form.id ? '修改成功!' : '新增成功!'))
      load() // 服务端权威：重拉列表，不做本地改数组
    }
    // 同名冲突等业务失败：后端 400 + 拦截器弹提示，页面不写 else
  } catch {
    // 网络/HTTP 层失败的提示已由拦截器统一弹出，这里只终结异常链
  } finally {
    formLoading.value = false
  }
}

// 删除：二次确认（catch 接住"取消"的 reject）→ 接口 → 页码回退防越界 → 重拉
async function handleDelete(row) {
  const ok = await ElMessageBox.confirm(`确认删除实验室 [${row.name}]？`, '确认删除', {
    type: 'warning',
  }).catch(() => false)
  if (!ok) return
  try {
    const res = await deleteLabApi(row.id)
    if (res.code >= 200 && res.code < 300) {
      // 删掉本页最后一条时回退一页，避免停在越界空页
      if (tableData.value.length === 1 && params.page > 1) {
        params.page -= 1
      }
      ElMessage.success(res.message || '删除成功！')
      load()
    }
  } catch {
    // 失败提示已由拦截器统一弹出，这里只终结异常链
  }
}
</script>

<template>
  <!-- 白卡：全宽列表卡（与 Users 同款），玻璃化透出粒子 -->
  <div class="labs-card">
    <h3 class="labs-title">实验室管理</h3>

    <!-- 搜索栏：回车与清空即时查询 -->
    <div class="labs-toolbar">
      <el-input
        v-model="params.keywords"
        placeholder="搜索名称或位置"
        clearable
        class="labs-toolbar__input"
        @keyup.enter="handleSearch"
        @clear="handleSearch"
      />
      <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
      <el-button type="success" :icon="Plus" @click="handleCreate">新增</el-button>
    </div>

    <el-table v-loading="loading" :data="tableData" style="width: 100%">
      <el-table-column prop="name" label="名称" min-width="140" />
      <el-table-column label="封面" width="90">
        <!-- el-image + preview-src-list：点缩略图弹出大图查看器；
             preview-teleported 把查看器挂到 body，避免被表格 overflow 裁切；fit=cover 防变形 -->
        <template #default="{ row }">
          <el-image
            v-if="row.img"
            :src="resolveBackendUrl(row.img)"
            :preview-src-list="[resolveBackendUrl(row.img)]"
            preview-teleported
            fit="cover"
            class="labs-cover"
          />
        </template>
      </el-table-column>
      <el-table-column prop="location" label="位置" min-width="110" />
      <el-table-column prop="capacity" label="容纳人数" width="90" />
      <el-table-column label="开放时间" width="120">
        <!-- 两值拼接：任一缺失显示 '-'；后端 open_time 是 time 类型，返回 "08:00:00"，
             slice(0,5) 截成 "08:00"（若后端本来只给 HH:mm，截断也是原值，幂等） -->
        <template #default="{ row }">
          {{
            row.open_time && row.close_time
              ? `${row.open_time.slice(0, 5)} - ${row.close_time.slice(0, 5)}`
              : '-'
          }}
        </template>
      </el-table-column>
      <el-table-column prop="description" label="简介" min-width="200">
        <!-- 不用 show-overflow-tooltip：EP 表格的内置 tooltip 会在跨行移动鼠标时锚定到上一个单元格，
             提示框飘到别的行/列上（截图里就出现在状态列右侧）。改成两行截断 + 原生 title，
             原生 title 永远跟着光标走，位置不会错 -->
        <template #default="{ row }">
          <span class="labs-desc" :title="row.description">{{ row.description }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.status === 1 ? 'success' : 'danger'">
            {{ row.status === 1 ? '开启' : '关闭' }}
          </el-tag>
        </template>
      </el-table-column>
      <!-- 操作列 170px：两个 text bg 按钮实测约 152px（含单元格左右 12px 内边距），150 会挤成两行 -->
      <el-table-column label="操作" width="170" class-name="labs-actions">
        <template #default="{ row }">
          <el-button type="primary" text bg @click="handleEdit(row)">编辑</el-button>
          <el-button type="danger" text bg @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页：与 Users 同款完整 layout -->
    <div class="labs-pager">
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

  <!-- 弹窗：520px 给 textarea/双时间选择器留空间；label 精简为 2-4 字 + 90px 标签列，整齐不折行 -->
  <!-- append-to-body：卡片的 backdrop-filter 会劫持 position:fixed，弹窗必须挂到 body 才按视口定位 -->
  <el-dialog v-model="dialogVisible" :title="form.id ? '编辑实验室' : '新增实验室'" width="520px" append-to-body>
    <el-form
      ref="dialogFormRef"
      :model="form"
      :rules="dialogRules"
      label-width="90px"
      v-loading="formLoading"
      @submit.prevent
    >
      <el-form-item label="封面">
        <!-- 上传触发区：有封面显示 80px 预览（过 resolveBackendUrl），没有显示按钮 -->
        <el-upload
          :http-request="handleFileUpload"
          :show-file-list="false"
          :before-upload="beforeCoverUpload"
          accept="image/jpeg,image/png,image/gif,image/webp"
        >
          <img
            v-if="form.img"
            :src="resolveBackendUrl(form.img)"
            class="labs-cover--edit"
            alt="封面预览"
          />
          <el-button v-else type="primary" plain>上传封面</el-button>
        </el-upload>
      </el-form-item>
      <el-form-item label="名称" prop="name">
        <el-input
          v-model="form.name"
          placeholder="请输入实验室名称"
          maxlength="50"
          show-word-limit
        />
      </el-form-item>
      <el-form-item label="位置">
        <el-input v-model="form.location" placeholder="请输入位置" maxlength="100" />
      </el-form-item>
      <el-form-item label="容纳人数">
        <!-- el-input-number：数值边界由组件锁死（:min/:max 必须冒号绑数字；placeholder/maxlength 它不支持） -->
        <el-input-number v-model="form.capacity" :min="1" :max="500" />
      </el-form-item>
      <el-form-item label="开放时间">
        <!-- 双 time-picker 定宽并排；format 管显示、value-format 管绑定值（必须 HH:mm 字符串，否则提交 Date 对象） -->
        <el-time-picker
          v-model="form.open_time"
          format="HH:mm"
          value-format="HH:mm"
          placeholder="开始"
          style="width: 130px"
        />
        <span class="labs-time-sep">至</span>
        <el-time-picker
          v-model="form.close_time"
          format="HH:mm"
          value-format="HH:mm"
          placeholder="结束"
          style="width: 130px"
        />
      </el-form-item>
      <el-form-item label="简介">
        <!-- textarea：rows 定高；maxlength 与后端 String(500) 对齐并显示计数 -->
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="3"
          maxlength="500"
          show-word-limit
          placeholder="请输入简介"
        />
      </el-form-item>
      <el-form-item label="状态">
        <el-radio-group v-model="form.status">
          <el-radio :value="1">开启</el-radio>
          <el-radio :value="0">关闭</el-radio>
        </el-radio-group>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="formLoading" @click="handleSave">确定</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
/* 白卡：与 Users 列表页同款令牌与玻璃化 */
.labs-card {
  padding: 24px;
  background-color: var(--color-surface-glass);
  backdrop-filter: blur(12px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}

.labs-title {
  margin: 0 0 16px;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.labs-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.labs-toolbar__input {
  width: 240px;
}

/* 表格透明化：与 Users 同款 */
.labs-card :deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(245, 247, 250, 0.7);
}

/* 简介两行截断：比单行省略号多看一倍内容，全文交给原生 title（不再用会跑位的内置 tooltip） */
.labs-desc {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 22px;
}

/* 操作列禁止换行：按钮实际宽度受 EP 内边距影响，170px 定宽 + nowrap 双保险，杜绝"编辑/删除上下叠" */
.labs-card :deep(.labs-actions .cell) {
  white-space: nowrap;
}

/* 缩略图：定尺寸圆角；cursor 由 el-image 预览态自带 */
.labs-cover {
  width: 50px;
  height: 50px;
  border-radius: 6px;
  display: block;
}

/* 弹窗封面预览：大一号 + 手型，提示可点击更换 */
.labs-cover--edit {
  width: 80px;
  height: 80px;
  border-radius: 6px;
  object-fit: cover;
  display: block;
  cursor: pointer;
}

/* 双时间选择器中间的"至"字间距 */
.labs-time-sep {
  margin: 0 8px;
  color: var(--color-text-muted);
}

.labs-pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
