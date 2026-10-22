<script setup>
// 我的预约（学生视角，管理员进来看到的是全部——后端按角色过滤，本页不判断身份）
// 骨架与 Users/Lab/Equipment 同一族列表页，但没有新增/编辑：只有"查 + 取消"两个动作
import { onMounted, reactive, ref } from 'vue'
// ElMessage 取消成功提示；ElMessageBox 取消前二次确认
import { ElMessage, ElMessageBox } from 'element-plus'
// 列表与取消两个接口（契约来自后端 reservation_router.py，取消是 PATCH）
import { cancelReservationApi, getReservationPageListApi } from '@/api/reservation'

// ===== 状态码 → 文案 / 颜色 的查表映射（本项目第一次出现四态）=====
// 用 ?? 而不是 ||：只有查不到（undefined）才兜底，避免将来出现空串文案时被误替换
const statusText = (status) => ({ 0: '待审核', 1: '已通过', 2: '已拒绝', 3: '已取消' })[status] ?? '-'
const statusType = (status) =>
  ({ 0: 'warning', 1: 'success', 2: 'danger', 3: 'info' })[status] ?? 'info'

// 可取消判定：与后端 reservation_services.cancel_reservation 对齐——
// 待审核(0) 与 已通过(1) 都允许本人取消；已拒绝(2)、已取消(3) 是终态。
// 后端另有两条时间闸（预约已开始、距开始不足 1 小时）不在这里预判：
// 那要用浏览器本地时钟去比服务端时区（后端显式按 UTC+8 判定），猜错只会让按钮莫名消失，
// 交给后端返回原文提示更准（"预约已经开始，不能取消！Ovo!" / "距离预约开始不足一小时…"）
const canCancel = (row) => row.status === 0 || row.status === 1

// ===== 查询参数 =====
const params = reactive({
  page: 1, // 当前页码：换筛选条件时重置回 1
  pageSize: 10, // 每页条数：提交时翻译成 page_size
  // 状态筛选：初值 null = 不筛。选「待审核」传的是数字 0（:value 冒号不能省，否则成字符串）
  status: null,
})

const tableData = ref([]) // 当前页数据
const total = ref(0) // 总条数
const loading = ref(false) // 表格区遮罩

// 加载当前页：挂载 / 换页 / 换筛选 / 取消成功后都汇到这里重拉
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
      // ?? [] 兜底：后端空列表给 null 时 v-for / el-table 会报错
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

// 取消预约：二次确认 → PATCH → 重拉列表
// 按钮只对 canCancel 的行为显示；"是不是本人""是否还来得及"由后端判（会返回原文提示）
async function handleCancel(row) {
  // 确认文案带上类型：设备预约只写实验室名会让人误以为取消了整间实验室
  const target = row.equipment_name ? `${row.lab_name} / ${row.equipment_name}` : row.lab_name
  // confirm 点"取消"是 reject：catch 转 false 接住，否则就是 Uncaught (in promise)
  const ok = await ElMessageBox.confirm(`确认取消 [${target}] 的预约？`, '确认取消', {
    type: 'warning',
  }).catch(() => false)
  if (!ok) return
  try {
    const res = await cancelReservationApi(row.id)
    if (res.code >= 200 && res.code < 300) {
      ElMessage.success(res.message || '取消成功！')
      load() // 服务端权威：重拉列表，不本地把 status 改成 3
    }
    // 非"本人/待审核"等业务失败：拦截器已弹后端原文，页面不写 else
  } catch {
    // 失败提示已由拦截器统一弹出，这里只终结异常链
  }
}

// 挂载即拉第一页
onMounted(() => {
  load()
})
</script>

<template>
  <!-- 玻璃卡：与 Users/Lab/Equipment 同款外壳 -->
  <div class="myres-card">
    <h3 class="myres-title">我的预约记录</h3>

    <!-- 筛选栏：一个状态下拉 + 查询（本页没有关键词搜索，后端 /list 也不收 keywords） -->
    <div class="myres-toolbar">
      <!-- clearable 清空 → undefined → axios 不发 status 参数 → 后端不过滤 = 看全部状态 -->
      <el-select
        v-model="params.status"
        placeholder="全部状态"
        clearable
        class="myres-toolbar__select"
        @change="handleSearch"
      >
        <!-- :value 必须冒号绑数字：写成 value="0" 会变字符串，与后端 int 及本页严格比较都不匹配 -->
        <el-option :value="0" label="待审核" />
        <el-option :value="1" label="已通过" />
        <el-option :value="2" label="已拒绝" />
        <el-option :value="3" label="已取消" />
      </el-select>
      <el-button type="primary" @click="handleSearch">查询</el-button>
    </div>

    <el-table v-loading="loading" :data="tableData" style="width: 100%">
      <el-table-column prop="lab_name" label="实验室" min-width="130" />
      <el-table-column label="预约类型" width="100">
        <!-- type 不入库，后端按 equipment_id 现算："设备" / "实验室" -->
        <template #default="{ row }">
          <el-tag :type="row.type === '实验室' ? 'success' : 'primary'">{{ row.type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="设备" min-width="110">
        <!-- 只约实验室时 equipment_name 为 null → 显示 '-'，不留空白格 -->
        <template #default="{ row }">{{ row.equipment_name || '-' }}</template>
      </el-table-column>
      <el-table-column prop="date" label="日期" width="110" />
      <el-table-column label="预约时段" width="120">
        <!-- 后端 start_time/end_time 是 time 类型，返回 "09:00:00"，slice(0,5) 截成 "09:00" -->
        <template #default="{ row }">
          {{
            row.start_time && row.end_time
              ? `${row.start_time.slice(0, 5)} - ${row.end_time.slice(0, 5)}`
              : '-'
          }}
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="160">
        <!-- 两行截断 + 原生 title：不用 show-overflow-tooltip（内置 tooltip 跨行会锚错单元格） -->
        <template #default="{ row }">
          <span class="myres-remark" :title="row.remark">{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="预约状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <!-- 操作列：v-if 而不是 :disabled——终态记录根本没有"取消"这个动作 -->
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button v-if="canCancel(row)" type="danger" text bg @click="handleCancel(row)">
            取消
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 空状态：一条预约都没有时给明确提示，而不是一张空表 -->
    <el-empty v-if="!loading && !tableData.length" description="还没有预约记录" />

    <!-- 分页：与另几页同款（含每页条数切换；改条数回第 1 页） -->
    <div class="myres-pager">
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
.myres-card {
  padding: 24px;
  background-color: var(--color-surface-glass);
  backdrop-filter: blur(12px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}

.myres-title {
  margin: 0 0 16px;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.myres-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.myres-toolbar__select {
  width: 200px;
}

/* 表格透明化：与另几页同款 */
.myres-card :deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(245, 247, 250, 0.7);
}

/* 备注两行截断，全文交给原生 title */
.myres-remark {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 22px;
}

.myres-pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
