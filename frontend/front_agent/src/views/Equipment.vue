<script setup>
// 设备管理页（CRUD 完整版）：列表 + 实验室筛选 + 双模式弹窗（新增/编辑）+ 图片上传 + 删除确认
// 与 Lab.vue 同一套骨架（第三次复用）。本章真正的增量只有两处：
//   ① lab_id 外键：必填，值从"实验室下拉"里选出来，提交给后端
//   ② lab_name 只读：后端关联查询算出来的展示字段，表格直显即可（前端不自己拼，避免两套真相）
import { onMounted, reactive, ref } from 'vue'
// 图片相对路径（/uploads/xxx）转绝对 URL：表格缩略图、弹窗预览都要过它
import { resolveBackendUrl } from '@/utils/url'
// ElMessage 轻提示；ElMessageBox 删除前二次确认
import { ElMessage, ElMessageBox } from 'element-plus'
// Plus/Search：工具栏按钮图标
import { Plus, Search } from '@element-plus/icons-vue'
// 设备 CRUD 四接口（封装在 api/equipment.js，契约来自后端 equipment_router.py）
import {
  createEquipmentApi,
  deleteEquipmentApi,
  getEquipmentPageListApi,
  updateEquipmentApi,
} from '@/api/equipment'
// 实验室下拉复用实验室的分页接口（借分页当全量用；page_size 上限 100 由后端 Query(le=100) 卡死）
import { getLabPageListApi } from '@/api/lab'
// 设备图片上传复用文件接口（与头像、实验室封面同一个端点）
import { uploadFileApi } from '@/api/file'

// ===== 列表区 =====
// 查询参数：搜索框 / 实验室筛选 / 分页器 / load 四处共用同一对象
const params = reactive({
  page: 1, // 当前页码：搜索或换筛选条件时重置回 1
  pageSize: 10, // 每页条数：提交时翻译成 page_size
  keywords: '', // 模糊搜索词：后端按设备 name 匹配（不含说明和型号规格）
  // 实验室筛选：初值用 undefined 而不是 ''——
  // el-select clearable 清空后也是 undefined，axios 会跳过 null/undefined 参数（不拼进查询串），
  // 后端拿不到 lab_id 就用默认 None → 不加过滤 = 查全部；若手动赋 ''，会发出 lab_id= 空串 → 后端 int 解析 422
  lab_id: undefined,
})

// 列表页三态
const tableData = ref([]) // 当前页行数据
const total = ref(0) // 总条数（后端统计）
const loading = ref(false) // 表格区 v-loading 遮罩

// 实验室下拉数据：一份数组两处消费（查询栏筛选 + 弹窗选择），所以单独一个 ref
const labOptions = ref([])

// 加载当前页：挂载 / 换页 / 搜索 / 换筛选 / 增删改成功后都汇到这里重拉
async function load() {
  loading.value = true
  try {
    const res = await getEquipmentPageListApi({
      page: params.page,
      // 字段翻译点：前端 camelCase → 查询串 snake_case（lab_id 本来就同名，直传）
      page_size: params.pageSize,
      keywords: params.keywords,
      lab_id: params.lab_id,
    })
    // 成功判定统一 2xx 区间（后端 create 返回 201，=== 200 会误判）
    if (res.code >= 200 && res.code < 300) {
      // ?? [] 兜底：后端空列表可能给 null，el-table 的 :data 必须是数组
      tableData.value = res.data?.list ?? []
      total.value = res.data?.total ?? 0
    }
  } catch {
    // 网络/HTTP 层失败的提示已由 request.js 拦截器统一弹出，这里只终结异常链，故意留空
  } finally {
    loading.value = false
  }
}

// 加载实验室下拉：只在挂载时拉一次（现阶段实验室远少于 100 间，够用）
async function loadLabs() {
  try {
    const res = await getLabPageListApi({ page: 1, page_size: 100 })
    if (res.code >= 200 && res.code < 300) {
      // ?? [] 兜底：null 会让两处 v-for 直接报错
      labOptions.value = res.data?.list ?? []
    }
  } catch {
    // 失败提示已由拦截器弹出；下拉空着不影响列表本身，故不额外处理
  }
}

// 搜索/换筛选：结果集变了必须回第 1 页——停在第 5 页筛小结果集会看到空表，误判"筛选坏了"
function handleSearch() {
  params.page = 1
  load()
}

// 挂载：先拉下拉、再拉列表（两个请求互不依赖，谁先返回都行）
onMounted(() => {
  loadLabs()
  load()
})

// ===== 弹窗区（新增/编辑共用一份表单） =====
const dialogVisible = ref(false) // 弹窗开关
const formLoading = ref(false) // 弹窗提交/上传 loading（与列表 loading 分开，各罩各的区域）
const dialogFormRef = ref(null) // 弹窗表单引用

// 弹窗表单：字段名与后端契约同名（snake_case），与 Lab.vue 现在的风格一致
// id 有无 = 编辑/新增模式开关；lab_id 初值 undefined，el-select 才会显示 placeholder 而不是空选中
const form = reactive({
  id: null,
  lab_id: undefined,
  name: '',
  spec: '',
  quantity: 1, // 默认 1：el-input-number 锁死 1-999，永远有值
  img: '', // 图片：上传成功写入相对路径 /uploads/xxx
  description: '',
  status: 1, // 1 正常 / 0 维修（码值与另两页一致，文案按设备业务域走）
})

// 校验规则：lab_id 必填（后端 Field(gt=0)）；name 必填（后端 min_length=1）
// quantity 不写 required——el-input-number 的边界已保证它永远有值，写了是死规则
const dialogRules = {
  lab_id: [{ required: true, message: '请选择所属实验室', trigger: 'change' }],
  name: [{ required: true, message: '请输入设备名称', trigger: 'blur' }],
}

// 载荷白名单：只提交后端 Schema 收的七个字段
// 不含 id（走 URL 路径）、不含 lab_name（后端关联查询的只读字段，回传无意义）
// create/update 共用这一份，避免"一条路翻译了另一条路忘了"（Lab 页踩过）
function buildEquipmentPayload() {
  return {
    lab_id: form.lab_id,
    name: form.name,
    spec: form.spec,
    quantity: form.quantity,
    img: form.img,
    description: form.description,
    status: form.status,
  }
}

// 重置：每次打开弹窗第一步，杜绝上一条残留；顺带清校验红字
function resetForm() {
  Object.assign(form, {
    id: null,
    lab_id: undefined,
    name: '',
    spec: '',
    quantity: 1,
    img: '',
    description: '',
    status: 1,
  })
  // 弹窗内容懒渲染，首次打开时 ref 还是 null，?. 防身
  dialogFormRef.value?.clearValidate()
}

// 新增：重置 → 开弹窗（lab_id 留空，逼用户显式选一个实验室）
function handleCreate() {
  resetForm()
  dialogVisible.value = true
}

// 编辑：重置 → 灌行数据（可空字段 ?? '' 兜底，避免 v-model 绑 null 让输入框行为怪异）
function handleEdit(row) {
  resetForm()
  Object.assign(form, {
    id: row.id,
    lab_id: row.lab_id,
    name: row.name,
    spec: row.spec ?? '',
    quantity: row.quantity ?? 1,
    img: row.img ?? '',
    description: row.description ?? '',
    status: row.status,
  })
  dialogVisible.value = true
}

// 上传前置校验：类型白名单 + 5MB 上限（与后端 MAX_UPLOAD_FILE_BYTES 一致，不跟教程的 2MB）
function beforeImageUpload(file) {
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

// 图片上传：:http-request 接管默认 XHR；罩的是弹窗（formLoading），不是列表
async function handleFileUpload({ file }) {
  formLoading.value = true
  try {
    const res = await uploadFileApi(file)
    if (res.code >= 200 && res.code < 300) {
      // 只写本地副本：上传 ≠ 落库，点确定保存才写进设备记录
      form.img = res.data?.url
      ElMessage.warning('图片已上传，点击确定保存后生效')
    }
  } catch {
    // 失败提示已由拦截器统一弹出，这里只终结异常链
  } finally {
    formLoading.value = false
  }
}

// 保存：校验 → 按 id 分流 create/update（载荷统一走白名单）→ 成功关弹窗重拉
async function handleSave() {
  const valid = await dialogFormRef.value.validate().catch(() => false)
  if (!valid) return
  formLoading.value = true
  try {
    const res = form.id
      ? await updateEquipmentApi(form.id, buildEquipmentPayload())
      : await createEquipmentApi(buildEquipmentPayload()) // 新增同样走白名单，绝不整包直发 form
    if (res.code >= 200 && res.code < 300) {
      dialogVisible.value = false
      ElMessage.success(res.message || (form.id ? '修改成功!' : '新增成功!'))
      load() // 服务端权威：重拉列表，不做本地改数组
    }
    // 同名(409)/实验室不存在(404)等业务失败：拦截器已弹后端 message，页面不写 else 防双重提示
  } catch {
    // 网络/HTTP 层失败的提示已由 request.js 拦截器统一弹出，这里只终结异常链
  } finally {
    formLoading.value = false
  }
}

// 删除：二次确认（catch 接住"取消"的 reject）→ 接口 → 页码回退防越界 → 重拉
async function handleDelete(row) {
  const ok = await ElMessageBox.confirm(`确认删除设备 [${row.name}]？`, '确认删除', {
    type: 'warning',
  }).catch(() => false)
  if (!ok) return
  try {
    const res = await deleteEquipmentApi(row.id)
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
  <!-- 玻璃卡：与 Lab/Users 同款全宽列表卡，粒子背景从卡后透出 -->
  <div class="eq-card">
    <h3 class="eq-title">实验室设备管理</h3>

    <!-- 查询栏：关键词 + 实验室筛选 + 查询 + 新增 -->
    <div class="eq-toolbar">
      <el-input
        v-model="params.keywords"
        placeholder="搜索设备名称"
        clearable
        class="eq-toolbar__input"
        @keyup.enter="handleSearch"
        @clear="handleSearch"
      />
      <!-- 实验室筛选：与弹窗里的选择下拉共用 labOptions，但绑的是 params.lab_id（不是 form.lab_id）
           clearable 清空 → undefined → axios 不发该参数 → 后端不过滤；@change 已覆盖清空场景，不必再写 @clear -->
      <el-select
        v-model="params.lab_id"
        placeholder="全部实验室"
        clearable
        class="eq-toolbar__select"
        @change="handleSearch"
      >
        <el-option v-for="item in labOptions" :key="item.id" :label="item.name" :value="item.id" />
      </el-select>
      <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
      <el-button type="success" :icon="Plus" @click="handleCreate">新增</el-button>
    </div>

    <el-table v-loading="loading" :data="tableData" style="width: 100%">
      <!-- lab_name：后端关联查询带出的只读字段，直显即可（不要拿 lab_id 去 labOptions 里 find 自己拼） -->
      <el-table-column prop="lab_name" label="所属实验室" min-width="130" />
      <el-table-column prop="name" label="设备名称" min-width="120" />
      <el-table-column label="图片" width="90">
        <!-- el-image + preview-src-list：点缩略图弹全屏大图查看器；preview-teleported 挂 body 防被表格裁切 -->
        <template #default="{ row }">
          <el-image
            v-if="row.img"
            :src="resolveBackendUrl(row.img)"
            :preview-src-list="[resolveBackendUrl(row.img)]"
            preview-teleported
            fit="cover"
            class="eq-img"
          />
        </template>
      </el-table-column>
      <el-table-column prop="spec" label="型号规格" min-width="120" />
      <el-table-column prop="quantity" label="数量" width="70" />
      <el-table-column prop="description" label="说明" min-width="180">
        <!-- 不用 show-overflow-tooltip：EP 内置 tooltip 跨行移动会锚错单元格（Lab 页实测过）
             改成两行截断 + 原生 title，原生 title 永远跟着光标走 -->
        <template #default="{ row }">
          <span class="eq-desc" :title="row.description">{{ row.description }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <!-- 设备域文案：1 正常 / 0 维修（码值同另两页，文案按业务域各页写死） -->
        <template #default="{ row }">
          <el-tag :type="row.status === 1 ? 'success' : 'danger'">
            {{ row.status === 1 ? '正常' : '维修' }}
          </el-tag>
        </template>
      </el-table-column>
      <!-- 操作列 170px + nowrap：两个 text bg 按钮实测约 152px（含单元格左右 12px 内边距），150 会挤成两行 -->
      <el-table-column label="操作" width="170" class-name="eq-actions">
        <template #default="{ row }">
          <el-button type="primary" text bg @click="handleEdit(row)">编辑</el-button>
          <el-button type="danger" text bg @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页：与 Lab/Users 同款完整 layout -->
    <div class="eq-pager">
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

  <!-- 弹窗：520px + 90px 标签列（与 Lab 同款；教程的 width="450" 无单位且很挤） -->
  <!-- append-to-body：卡片的 backdrop-filter 会劫持 position:fixed，弹窗必须挂到 body 才按视口定位 -->
  <el-dialog v-model="dialogVisible" :title="form.id ? '编辑设备' : '新增设备'" width="520px" append-to-body>
    <el-form
      ref="dialogFormRef"
      :model="form"
      :rules="dialogRules"
      label-width="90px"
      v-loading="formLoading"
      @submit.prevent
    >
      <!-- 字段顺序与教程略有差异：短字段（实验室/名称/规格/数量）成组在前，图片+说明这类长控件靠下，状态收尾
           理由：textarea 夹在短字段中间会把弹窗撑得忽长忽短。这是有意调整，不是照抄漏了 -->
      <el-form-item label="所属实验室" prop="lab_id">
        <!-- 必填外键：选项来自 labOptions，提交的是 item.id；lab_name 只是展示字段，不进表单 -->
        <el-select v-model="form.lab_id" placeholder="请选择实验室">
          <el-option v-for="item in labOptions" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="设备名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入设备名称" maxlength="50" show-word-limit />
      </el-form-item>
      <el-form-item label="型号规格">
        <el-input v-model="form.spec" placeholder="例如 24G 显存" maxlength="100" />
      </el-form-item>
      <el-form-item label="数量">
        <!-- 边界与后端契约一致：quantity Field(ge=1, le=999)；:min/:max 必须冒号绑数字 -->
        <el-input-number v-model="form.quantity" :min="1" :max="999" />
      </el-form-item>
      <el-form-item label="图片">
        <!-- 上传触发区：有图显示 80px 预览（过 resolveBackendUrl），没图显示按钮 -->
        <el-upload
          :http-request="handleFileUpload"
          :show-file-list="false"
          :before-upload="beforeImageUpload"
          accept="image/jpeg,image/png,image/gif,image/webp"
        >
          <img
            v-if="form.img"
            :src="resolveBackendUrl(form.img)"
            class="eq-img--edit"
            alt="设备图片"
          />
          <el-button v-else type="primary" plain>上传图片</el-button>
        </el-upload>
      </el-form-item>
      <el-form-item label="说明">
        <!-- textarea：rows 定高；maxlength 与后端 String(500) 对齐并显示计数 -->
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="3"
          maxlength="500"
          show-word-limit
          placeholder="请输入说明"
        />
      </el-form-item>
      <el-form-item label="状态">
        <!-- :value 绑数字 1/0：与后端 status 列类型一致（EP 2.6+ 用 value 而非 label 传值） -->
        <el-radio-group v-model="form.status">
          <el-radio :value="1">正常</el-radio>
          <el-radio :value="0">维修</el-radio>
        </el-radio-group>
      </el-form-item>
    </el-form>
    <template #footer>
      <!-- 取消必须接 @click：教程原型这里漏了绑定，点了完全没反应 -->
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="formLoading" @click="handleSave">确定</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
/* 白卡：与 Lab/Users 列表页同款令牌与玻璃化 */
.eq-card {
  padding: 24px;
  background-color: var(--color-surface-glass);
  backdrop-filter: blur(12px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}

.eq-title {
  margin: 0 0 16px;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
}

/* 查询栏：输入框 + 筛选下拉定宽，按钮并排，与表格留呼吸距 */
.eq-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.eq-toolbar__input {
  width: 200px;
}

.eq-toolbar__select {
  width: 180px;
}

/* 表格透明化：行背景交给卡片玻璃，表头保留淡灰维持层次 */
.eq-card :deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(245, 247, 250, 0.7);
}

/* 说明两行截断：全文交给原生 title */
.eq-desc {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 22px;
}

/* 操作列禁止换行：与 Lab 同款双保险 */
.eq-card :deep(.eq-actions .cell) {
  white-space: nowrap;
}

/* 缩略图：定尺寸圆角；cursor 由 el-image 预览态自带 */
.eq-img {
  width: 50px;
  height: 50px;
  border-radius: 6px;
  display: block;
}

/* 弹窗图片预览：大一号 + 手型，提示可点击更换 */
.eq-img--edit {
  width: 80px;
  height: 80px;
  border-radius: 6px;
  object-fit: cover;
  display: block;
  cursor: pointer;
}

/* 分页右对齐 */
.eq-pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
