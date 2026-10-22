<script setup>
// 预约审核（管理员页）：看全部预约、对"待审核"的记录做 通过 / 拒绝
// 与 MyReservation.vue 同族，差异有三处：多一列「预约人」、默认筛"待审核"、操作列换成两个按钮
// 两页不合并：差异是结构性的（列不同、动作不同、默认筛选不同），按项目判据"结构不同就先复制"
import { onMounted, reactive, ref } from 'vue'
// ElMessage 审核结果提示；ElMessageBox 审核前二次确认
import { ElMessage, ElMessageBox } from 'element-plus'
// 列表与审核两个接口（审核是 PATCH + body { status }，后端要求管理员身份）
import { auditReservationApi, getReservationPageListApi } from '@/api/reservation'

// ===== 状态码 → 文案 / 颜色 =====
// 与 MyReservation.vue 各留一份：10 行重复，换掉"为以后复用先建工具文件"的代价（项目已定：不建）
const statusText = (status) => ({ 0: '待审核', 1: '已通过', 2: '已拒绝', 3: '已取消' })[status] ?? '-'
const statusType = (status) =>
  ({ 0: 'warning', 1: 'success', 2: 'danger', 3: 'info' })[status] ?? 'info'

// ===== 查询参数 =====
const params = reactive({
  page: 1, // 当前页码
  pageSize: 10, // 每页条数：提交时翻译成 page_size
  // 默认只看待审核（审核页的默认视角）；清空 → undefined → 不发参数 → 看全部
  status: 0,
})

const tableData = ref([]) // 当前页数据
const total = ref(0) // 总条数
const loading = ref(false) // 表格区遮罩

// 加载当前页：挂载 / 换页 / 换筛选 / 审核成功后都汇到这里重拉
async function load() {
  loading.value = true
  try {
    const res = await getReservationPageListApi({
      page: params.page,
      // 字段翻译点：camelCase → 查询串 snake_case
      page_size: params.pageSize,
      status: params.status,
    })
    // 成功判定统一 2xx 区间（与拦截器口径一致）
    if (res.code >= 200 && res.code < 300) {
      // ?? [] 兜底：后端空列表给 null 时 el-table 的 :data 会报错
      tableData.value = res.data?.list ?? []
      total.value = res.data?.total ?? 0
    }
  } catch {
    // 网络/HTTP 层失败的提示已由 request.js 拦截器统一弹出，这里只终结异常链，故意留空
  } finally {
    loading.value = false
  }
}

// 换筛选/点查询：结果集变了必须回第 1 页
function handleSearch() {
  params.page = 1
  load()
}

// 审核：二次确认 → PATCH { status } → 重拉列表
// status 只接受 1（通过）/ 2（拒绝）；后端还要求记录当前是 0（待审核），已取消/已审的会被拒
async function handleAudit(row, status) {
  const action = status === 1 ? '通过' : '拒绝'
  // confirm 点"取消"是 reject：catch 转 false 接住，否则就是 Uncaught (in promise)
  const ok = await ElMessageBox.confirm(
    `确认${action} [${row.user_name || row.user_id}] 的预约？`,
    '预约审核',
    { type: 'warning' },
  ).catch(() => false)
  if (!ok) return
  try {
    const res = await auditReservationApi(row.id, status)
    if (res.code >= 200 && res.code < 300) {
      ElMessage.success(res.message || `已${action}！`)
      load() // 服务端权威：重拉列表，不本地改 status
    }
    // 状态不符（已被别人审过）等业务失败：拦截器已弹后端原文，页面不写 else
  } catch {
    // 失败提示已由拦截器统一弹出，这里只终结异常链
  }
}

// 挂载即拉第一页（默认就是"待审核"这一屏）
onMounted(() => {
  load()
})
</script>

<template>
  <!-- 玻璃卡：与 MyReservation/Users/Lab 同款外壳（教程这里抄成了「我的预约记录」，标题必须改） -->
  <div class="audit-card">
    <h3 class="audit-title">预约审核</h3>

    <!-- 筛选栏：状态下拉默认「待审核」，清空即看全部 -->
    <div class="audit-toolbar">
      <el-select
        v-model="params.status"
        placeholder="全部状态"
        clearable
        class="audit-toolbar__select"
        @change="handleSearch"
      >
        <!-- :value 冒号绑数字：value="0" 会变字符串，与后端 int 及本页默认值 0 都不匹配 -->
        <el-option :value="0" label="待审核" />
        <el-option :value="1" label="已通过" />
        <el-option :value="2" label="已拒绝" />
        <el-option :value="3" label="已取消" />
      </el-select>
      <el-button type="primary" @click="handleSearch">查询</el-button>
    </div>

    <el-table v-loading="loading" :data="tableData" style="width: 100%">
      <!-- 管理员视角独有的一列：谁的预约 -->
      <el-table-column prop="user_name" label="预约人" min-width="100" />
      <el-table-column prop="lab_name" label="实验室" min-width="130" />
      <el-table-column label="预约类型" width="100">
        <!-- type 不入库，后端按 equipment_id 现算："设备" / "实验室" -->
        <template #default="{ row }">
          <el-tag :type="row.type === '实验室' ? 'success' : 'primary'">{{ row.type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="设备" min-width="110">
        <template #default="{ row }">{{ row.equipment_name || '-' }}</template>
      </el-table-column>
      <el-table-column prop="date" label="日期" width="110" />
      <el-table-column label="预约时段" width="120">
        <!-- 后端 time 类型返回 "09:00:00"，slice(0,5) 截秒 -->
        <template #default="{ row }">
          {{
            row.start_time && row.end_time
              ? `${row.start_time.slice(0, 5)} - ${row.end_time.slice(0, 5)}`
              : '-'
          }}
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="140">
        <!-- 两行截断 + 原生 title（内置 tooltip 会跨行锚错单元格） -->
        <template #default="{ row }">
          <span class="audit-remark" :title="row.remark">{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="预约状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <!-- 操作列 180px + nowrap：两个按钮并排的宽度算法与 Lab/Equipment 同款 -->
      <el-table-column label="操作" width="180" class-name="audit-actions">
        <template #default="{ row }">
          <!-- <template v-if> 包住两个按钮：不产生额外 DOM 节点，一组元素同进同出 -->
          <template v-if="row.status === 0">
            <el-button type="success" text bg @click="handleAudit(row, 1)">通过</el-button>
            <el-button type="danger" text bg @click="handleAudit(row, 2)">拒绝</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <!-- 空状态：默认筛"待审核"时最容易一条都没有，必须给提示而不是空表 -->
    <el-empty v-if="!loading && !tableData.length" description="没有符合条件的预约" />

    <!-- 分页：与另几页同款（含每页条数切换；改条数回第 1 页） -->
    <div class="audit-pager">
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
</template>

<style scoped>
/* 外壳：manager 子页面族同款玻璃卡 */
.audit-card {
  padding: 24px;
  background-color: var(--color-surface-glass);
  backdrop-filter: blur(12px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}

.audit-title {
  margin: 0 0 16px;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.audit-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.audit-toolbar__select {
  width: 200px;
}

/* 表格透明化：与另几页同款 */
.audit-card :deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(245, 247, 250, 0.7);
}

/* 备注两行截断，全文交给原生 title */
.audit-remark {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 22px;
}

/* 操作列禁止换行：与 Lab/Equipment 同款双保险 */
.audit-card :deep(.audit-actions .cell) {
  white-space: nowrap;
}

.audit-pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
