<script setup>
// 学生端某间实验室的设备列表（只读页）：从 Lablist 带 lab_id 跳进来
// 与 Lablist 同属学生端：没有弹窗、没有增删改；多出来的部分是"顶部实验室信息条"（用详情接口补上下文）
import { onMounted, reactive, ref, watch } from 'vue'
// useRoute 读当前地址的 query（?lab_id=3）；useRouter 负责跳回列表页
import { useRoute, useRouter } from 'vue-router'
// 设备图片相对路径转绝对 URL（不转则 5173 下裂图）
import { resolveBackendUrl } from '@/utils/url'
// ElMessage：本页只用于"缺 lab_id"的参数校验提示；预约提交的成功/失败提示归弹窗与拦截器
import { ElMessage } from 'element-plus'
// Picture：卡片无图/图加载失败时的占位图标
import { Picture } from '@element-plus/icons-vue'
// 实验室详情：顶部信息条的数据源（学生只能看到开放中的，后端按角色强制）
import { getLabApi } from '@/api/lab'
// 设备分页：按 lab_id 过滤（维修中的也返回，页面上用 tag + 禁用按钮表达"不能约"）
import { getEquipmentPageListApi } from '@/api/equipment'
// 预约弹窗：与 Lablist 共用的业务组件
import ReserveDialog from '@/components/ReserveDialog.vue'

const route = useRoute()
const router = useRouter()

// ===== 路由参数 =====
// URL 上的值永远是字符串："3" → Number → 3，才能和后端返回的数字 lab_id 比较
// 取不到时 Number(undefined) = NaN，NaN 是假值，正好被下面的 !params.lab_id 兜住
const params = reactive({
  page: 1, // 当前页码
  pageSize: 10, // 每页条数：提交时翻译成 page_size
  lab_id: Number(route.query.lab_id), // 所属实验室：本页所有查询的锚点
})

// 页面状态：lab 是详情对象（null = 还没加载/不存在/无权访问），tableData 是设备分页
const lab = ref(null)
const tableData = ref([])
const total = ref(0)
const loading = ref(false) // 只罩设备卡片墙，信息条单独由 lab 决定显隐

// ===== 预约弹窗状态 =====
// 与 Lablist 同一套：开关归本页，"约哪台设备"也归本页（弹窗只读 props，不自己决定）
const reserveVisible = ref(false)
const currentEquipment = ref(null) // null = 只约实验室；有值 = 约这台设备

// 加载实验室详情：顶部信息条用
async function loadLab() {
  // 缺 lab_id 直接拦下：不发请求，避免后端 422/404 的空转
  if (!params.lab_id) {
    ElMessage.error('缺少实验室查询条件 [lab_id]')
    return
  }
  try {
    const res = await getLabApi(params.lab_id)
    if (res.code >= 200 && res.code < 300) {
      lab.value = res.data
    }
    // 学生访问已关闭的实验室：后端 404「实验室不存在或当前不可访问」，拦截器已弹提示，
    // lab 保持 null → 信息条不渲染、表格走空状态，页面不崩
  } catch {
    // 网络/HTTP 层失败的提示已由 request.js 拦截器统一弹出，这里只终结异常链
  }
}

// 加载设备分页：本页主数据
async function loadEquipment() {
  if (!params.lab_id) return // 与 loadLab 同一个闸门，这里静默返回（错误提示只弹一次）
  loading.value = true
  try {
    const res = await getEquipmentPageListApi({
      page: params.page,
      // 字段翻译点：camelCase → 查询串 snake_case
      page_size: params.pageSize,
      lab_id: params.lab_id,
    })
    if (res.code >= 200 && res.code < 300) {
      // ?? [] 兜底：后端空列表可能给 null，v-for 绑 null 会直接报错
      tableData.value = res.data?.list ?? []
      total.value = res.data?.total ?? 0
    }
  } catch {
    // 失败提示已由拦截器统一弹出，这里只终结异常链
  } finally {
    loading.value = false
  }
}

// 换页/换条数：与另四页同款（换页直接重拉，换条数回第 1 页）
function handleSearch() {
  params.page = 1
  loadEquipment()
}

// 预约实验室 / 预约设备：共用同一个弹窗，差别只在 currentEquipment 有没有值
// （弹窗据此切换标题「预约实验室 / 预约设备」，并在载荷里决定 equipment_id 传不传）
function handleReserveLab() {
  currentEquipment.value = null // 清空 = 这次只约实验室
  reserveVisible.value = true
}

function handleReserveEquipment(row) {
  currentEquipment.value = row // 记住这台设备：弹窗要它的 id 和 name
  reserveVisible.value = true
}

// 返回实验室列表：学生端的"上一页"，硬编码路径与菜单 index 保持一致
function handleBack() {
  router.push('/manager/lablist')
}

// 同一个组件实例内换 lab_id（浏览器前进/后退、或从别的实验室点进来）时，
// vue-router 会复用组件、onMounted 不再触发——不监听 query 就会看到上一间实验室的数据
watch(
  () => route.query.lab_id,
  (val) => {
    params.lab_id = Number(val)
    params.page = 1
    lab.value = null
    tableData.value = []
    currentEquipment.value = null // 换实验室后，上一间选的设备已失效，防误提交
    loadLab()
    loadEquipment()
  },
)

// 挂载即拉两个互不依赖的请求（谁先返回都行，各管各的区域）
onMounted(() => {
  loadLab()
  loadEquipment()
})
</script>

<template>
  <!-- 玻璃卡：与 Lablist/Lab/Equipment 同款外壳 -->
  <div class="labeq-card">
    <!-- 头部：标题带实验室名 + 两个动作按钮（教程把按钮塞进 el-card header，我们放进卡片首行） -->
    <div class="labeq-head">
      <h3 class="labeq-title">{{ lab?.name ?? '实验室' }} · 设备列表</h3>
      <div class="labeq-head__actions">
        <el-button type="primary" @click="handleReserveLab">预约实验室</el-button>
        <el-button @click="handleBack">返回实验室列表</el-button>
      </div>
    </div>

    <!-- 实验室信息条：只有拿到详情才渲染（lab 为 null 时整块不生成 DOM，不会显示 "null"） -->
    <div v-if="lab" class="labeq-brief">
      <!-- 可空字段一律兜底：description/location 后端允许 null -->
      <div class="labeq-brief__row">简介：{{ lab.description || '-' }}</div>
      <div class="labeq-brief__row">
        位置：{{ lab.location || '-' }} ｜ 容纳人数： {{ lab.capacity }} 人 ｜ 开放时间：{{
          lab.open_time && lab.close_time
            ? `${lab.open_time.slice(0, 5)} - ${lab.close_time.slice(0, 5)}`
            : '-'
        }}
      </div>
    </div>

    <!-- 设备卡片墙（替代表格）：图片是设备页信息量最大的元素，表格的 90px 缩略图列把它浪费了
         维修中的也展示（学生需要知道哪些不能用），用角标 + tag + 禁用按钮三重表达 -->
    <div v-loading="loading" class="labeq-grid">
      <div v-for="row in tableData" :key="row.id" class="labeq-item">
        <!-- 图片区固定 4:3：有图用 el-image（点图看大图，站点约定），加载失败走 #error 槽回落到占位 -->
        <div class="labeq-item__media">
          <el-image
            v-if="row.img"
            :src="resolveBackendUrl(row.img)"
            :preview-src-list="[resolveBackendUrl(row.img)]"
            preview-teleported
            fit="cover"
            class="labeq-item__img"
          >
            <template #error>
              <div class="labeq-item__ph">
                <el-icon><Picture /></el-icon>
                <span>图片加载失败</span>
              </div>
            </template>
          </el-image>
          <div v-else class="labeq-item__ph">
            <el-icon><Picture /></el-icon>
            <span>暂无图片</span>
          </div>
          <!-- 维修角标压图片右上角：不读文字也能一眼扫出哪些不能约 -->
          <span v-if="row.status !== 1" class="labeq-item__flag">维修中</span>
        </div>

        <div class="labeq-item__body">
          <!-- 名称/规格单行截断，全文交给 title -->
          <div class="labeq-item__name" :title="row.name">{{ row.name }}</div>
          <div class="labeq-item__spec" :title="row.spec">{{ row.spec || '-' }}</div>
          <div class="labeq-item__meta">
            <span class="labeq-item__count">数量 {{ row.quantity }}</span>
            <!-- 设备域文案：1 正常 / 0 维修（码值同管理员页，文案按业务域） -->
            <el-tag :type="row.status === 1 ? 'success' : 'danger'" size="small">
              {{ row.status === 1 ? '正常' : '维修' }}
            </el-tag>
          </div>
          <!-- 整宽预约按钮：比表格操作列里的小按钮醒目；:disabled="!row.status" 维修中不能约 -->
          <el-button
            class="labeq-item__btn"
            type="primary"
            :disabled="!row.status"
            @click="handleReserveEquipment(row)"
          >
            预约
          </el-button>
        </div>
      </div>
    </div>

    <!-- 空状态：缺 lab_id / 实验室不可访问 / 这间真没设备，三种情况都落到这里 -->
    <el-empty v-if="!loading && !tableData.length" description="暂无设备" />

    <!-- 分页：与另四页同款 -->
    <div class="labeq-pager">
      <el-pagination
        v-model:current-page="params.page"
        v-model:page-size="params.pageSize"
        :total="total"
        :page-sizes="[10, 20, 50]"
        background
        layout="total, sizes, prev, pager, next"
        @current-change="loadEquipment"
        @size-change="handleSearch"
      />
    </div>

    <!-- 预约弹窗：lab 相关 props 一直传（信息条有值就说明实验室拿到了）；
         equipment 两个 props 只在点了某台设备的「预约」时才有值 → 弹窗据此切标题与载荷 -->
    <ReserveDialog
      v-model:visible="reserveVisible"
      :lab-id="lab?.id"
      :lab-name="lab?.name"
      :equipment-id="currentEquipment?.id"
      :equipment-name="currentEquipment?.name"
    />
  </div>
</template>

<style scoped>
/* 外壳：manager 子页面族同款玻璃卡 */
.labeq-card {
  padding: 24px;
  background-color: var(--color-surface-glass);
  backdrop-filter: blur(12px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}

/* 头部：标题与按钮两端对齐 */
.labeq-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.labeq-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
}

/* 实验室信息条：品牌淡紫底 + 左侧渐变竖条，和页面标题同一套语言 */
.labeq-brief {
  padding: 14px 16px;
  margin-bottom: 18px;
  background: var(--gradient-accent-soft);
  border: 1px solid rgba(79, 110, 247, 0.12);
  border-left: 3px solid var(--color-accent);
  border-radius: 12px;
}

.labeq-brief__row {
  font-size: 13px;
  line-height: 1.8;
  color: var(--color-text-secondary);
}

/* 卡片墙：auto-fill + minmax 让列数随容器宽度自适应（够 220px 就多一列），不用手写断点 */
.labeq-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
  min-height: 120px;
}

.labeq-item {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: #fff;
  border: 1px solid var(--color-border);
  border-radius: 14px;
  box-shadow: 0 1px 2px rgba(23, 35, 61, 0.04);
  transition: var(--transition-base);
}

/* hover 上浮 + 品牌色阴影：给"可看/可约"的暗示 */
.labeq-item:hover {
  border-color: rgba(79, 110, 247, 0.24);
  box-shadow: var(--shadow-card-hover);
  transform: translateY(-3px);
}

/* 图片区固定 4:3：所有卡片因此等高，格子才整齐 */
.labeq-item__media {
  position: relative;
  aspect-ratio: 4 / 3;
  overflow: hidden;
  background-color: #f4f7fd;
}

.labeq-item__img {
  display: block;
  width: 100%;
  height: 100%;
}

/* 图片悬停缓慢放大（.el-image 内部 img 需要 :deep 穿透） */
.labeq-item__img :deep(.el-image__inner) {
  transition: transform 0.45s cubic-bezier(0.22, 1, 0.36, 1);
}

.labeq-item:hover .labeq-item__img :deep(.el-image__inner) {
  transform: scale(1.05);
}

/* 占位/加载失败态：淡蓝渐变 + 图标，避免出现空白方块 */
.labeq-item__ph {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  height: 100%;
  font-size: 12px;
  color: var(--color-text-muted);
  background: linear-gradient(135deg, #eef3ff, #e6ecfb);
}

/* 维修角标：橙色渐变胶囊，压在图片右上角 */
.labeq-item__flag {
  position: absolute;
  top: 10px;
  right: 10px;
  padding: 3px 10px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, #fb923c, #ef4444);
  border-radius: 999px;
  box-shadow: 0 6px 14px -6px rgba(239, 68, 68, 0.6);
}

.labeq-item__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  padding: 14px 16px 16px;
}

.labeq-item__name {
  overflow: hidden;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.labeq-item__spec {
  margin-top: 4px;
  overflow: hidden;
  font-size: 12px;
  color: var(--color-text-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.labeq-item__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
}

.labeq-item__count {
  font-size: 12px;
  color: var(--color-text-muted);
}

/* 整宽按钮钉在卡片底部：多张卡并排时按钮天然对齐 */
.labeq-item__btn {
  width: 100%;
  margin-top: 12px;
}

.labeq-pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
