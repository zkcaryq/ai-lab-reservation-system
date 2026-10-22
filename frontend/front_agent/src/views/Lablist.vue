<script setup>
// 学生端实验室列表（只读页）：搜索 + 卡片栅格 + 分页 + 跳转设备页 + 预约弹窗
// 与管理员页（Lab.vue）的区别：没有增删改表格，只有一个 load()；预约表单在共用组件 ReserveDialog 里
import { onMounted, reactive, ref } from 'vue'
// useRouter()：组合式路由。比教程的 `import router from '@/router'`（模块单例）更规范，
// 两者都能跑，但组件内跳转统一用这个，将来加守卫/测试替身更干净
import { useRouter } from 'vue-router'
// 封面相对路径（/uploads/xxx）转绝对 URL：不转的话 5173 端口下必裂图（本项目第 5 处复用）
import { resolveBackendUrl } from '@/utils/url'
// 提交/失败的提示都归 ReserveDialog 与 request.js 拦截器，本页不再需要 ElMessage
// Search：查询按钮图标
import { Search } from '@element-plus/icons-vue'
// 实验室分页查询：学生登录后同一个接口，后端按角色只返回开放中的实验室
import { getLabPageListApi } from '@/api/lab'
// 预约弹窗：本项目第一个业务共用组件（LabEquipment 页也用同一个）
import ReserveDialog from '@/components/ReserveDialog.vue'

const router = useRouter()

// ===== 查询参数 =====
// 命名与 Lab/Equipment/Users 三页保持一致：前端 camelCase，提交时翻译成后端的 snake_case
const params = reactive({
  page: 1, // 当前页码：搜索时重置回 1
  pageSize: 10, // 每页条数：提交时翻译成 page_size
  keywords: '', // 模糊搜索词：后端按实验室 name 匹配
})
// 关于 status（只看开放中的）：这里**故意不传**。
// 后端 lab_router.py 已按角色强制——admin 传什么看什么，学生固定 status=1。
// 前端再传一遍是重复逻辑，而且学生改请求就能绕过；权限落在后端才是真边界。

// 只读页三态：数据、总数、加载中
const tableData = ref([]) // 当前页数据（字段名沿用 tableData，与另三页对齐，便于以后抽公共逻辑）
const total = ref(0) // 后端统计的总条数，分页器据此算页数
const loading = ref(false) // 卡片区的 v-loading 遮罩

// ===== 预约弹窗状态 =====
// 弹窗自己只管"显示什么、怎么提交"；开/关由本页持有（reserveVisible），
// 点哪张卡的「预约」要把那间实验室记住（currentLab），弹窗才知道 lab_id / lab_name 传什么
const reserveVisible = ref(false)
const currentLab = ref(null)

// 加载当前页：挂载 / 换页 / 搜索成功后都汇到这里重拉
async function load() {
  loading.value = true
  try {
    const res = await getLabPageListApi({
      page: params.page,
      // 字段翻译点：camelCase → 查询串 snake_case（后端参数名是 page_size）
      page_size: params.pageSize,
      keywords: params.keywords,
    })
    // 成功判定统一 2xx 区间（与拦截器口径一致；教程这里写的是 === 200）
    if (res.code >= 200 && res.code < 300) {
      // ?? [] 兜底：后端空列表可能给 null，v-for 绑 null 会直接报错
      tableData.value = res.data?.list ?? []
      total.value = res.data?.total ?? 0
    }
  } catch {
    // 网络/HTTP 层失败的提示已由 request.js 拦截器统一弹出，这里只终结异常链，故意留空
  } finally {
    loading.value = false
  }
}

// 搜索：结果集变了必须回第 1 页——停在第 5 页搜小结果集会看到空列表
function handleSearch() {
  params.page = 1
  load()
}

// 查看设备：用 query 传 lab_id（?lab_id=3），目标页用 useRoute().query.lab_id 取
// 注意 URL 上的值永远是字符串，目标页要 Number() 转成数字再和后端返回值比较
// 路径必须与 router 里的 path 完全一致（我们盘上是 'labequipment'，教程写的是 'lab-equipment'）
function handleViewEquipment(lab) {
  router.push({ path: '/manager/labequipment', query: { lab_id: lab.id } })
}

// 预约：记住当前这间实验室 + 打开共用弹窗（弹窗从 props 拿 lab_id / lab_name，本页不拼载荷）
function handleReserve(lab) {
  currentLab.value = lab
  reserveVisible.value = true
}

// 挂载即拉第一页
onMounted(() => {
  load()
})
</script>

<template>
  <!-- 玻璃卡：与 Lab/Equipment/Users 同款外壳（粒子背景从卡后透出），不再用教程的 el-card 白底 -->
  <div class="lablist-card">
    <h3 class="lablist-title">实验室列表</h3>

    <!-- 搜索栏：只读页没有"新增"按钮，一个输入框 + 查询 -->
    <div class="lablist-toolbar">
      <el-input
        v-model="params.keywords"
        placeholder="请输入实验室名称查询"
        clearable
        class="lablist-toolbar__input"
        @keyup.enter="handleSearch"
        @clear="handleSearch"
      />
      <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
    </div>

    <!-- 卡片栅格：v-loading 罩这一区（搜索栏保持可操作）
         el-row 的 gutter 是列间距（靠负 margin 实现），所以不要再给它加 padding -->
    <el-row v-loading="loading" :gutter="16" class="lablist-grid">
      <!-- 响应式断点：手机 1 张、平板 2 张、笔记本 3 张、桌面 4 张（教程只有 :span="6"，窄屏会挤成一条） -->
      <el-col
        v-for="item in tableData"
        :key="item.id"
        :xs="24"
        :sm="12"
        :md="8"
        :lg="6"
        class="lablist-col"
      >
        <el-card shadow="hover" class="lablist-item">
          <!-- 封面：有图用 el-image（点一下看大图），没图给一块等高占位，保证卡片高度整齐 -->
          <el-image
            v-if="item.img"
            :src="resolveBackendUrl(item.img)"
            :preview-src-list="[resolveBackendUrl(item.img)]"
            preview-teleported
            fit="cover"
            class="lablist-cover"
            alt="实验室封面"
          />
          <div v-else class="lablist-cover lablist-cover--empty">暂无封面</div>

          <!-- 名称：固定两行高度，避免长名称把下面几行挤错位 -->
          <div class="lablist-name">{{ item.name }}</div>
          <!-- 可空字段一律兜底：后端 location 允许 null，不兜会显示 "位置：" 空着 -->
          <div class="lablist-meta">位置：{{ item.location || '-' }}</div>
          <div class="lablist-meta">容量：{{ item.capacity }} 人</div>
          <!-- 后端 open_time 是 time 类型，返回 "08:00:00"，slice(0,5) 截成 "08:00"（幂等） -->
          <div class="lablist-meta">
            开放时间：{{
              item.open_time && item.close_time
                ? `${item.open_time.slice(0, 5)} - ${item.close_time.slice(0, 5)}`
                : '-'
            }}
          </div>

          <!-- 按钮行：margin-top:auto 把它钉在卡片底部，多张卡并排时按钮天然对齐 -->
          <div class="lablist-actions">
            <el-button style="flex: 1" @click="handleViewEquipment(item)">查看设备</el-button>
            <el-button style="flex: 1" type="primary" @click="handleReserve(item)">预约</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 空状态：只读页第一次出现"可能一条都没有"的场景（学生视角下所有实验室都关闭时）
         教程这里是一片空白，用户会以为页面坏了 -->
    <el-empty v-if="!loading && !tableData.length" description="暂无可预约的实验室" />

    <!-- 分页：与另三页同款（total + 每页条数 + 上/页码/下）；改条数走 handleSearch 回第 1 页 -->
    <div class="lablist-pager">
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
    <!-- 预约弹窗（只约实验室，不传 equipment 相关 props → 弹窗标题走「预约实验室」分支）
         v-model:visible 展开 = :visible + @update:visible：开关的真相在本页，弹窗只发事件不擅自改 -->
    <ReserveDialog
      v-model:visible="reserveVisible"
      :lab-id="currentLab?.id"
      :lab-name="currentLab?.name"
    />
  </div>
</template>

<style scoped>
/* 外壳：manager 子页面族同款玻璃卡 */
.lablist-card {
  padding: 24px;
  background-color: var(--color-surface-glass);
  backdrop-filter: blur(12px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}

.lablist-title {
  margin: 0 0 16px;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.lablist-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.lablist-toolbar__input {
  width: 240px;
}

/* 栅格区：给 v-loading 一个有高度的容器，加载时遮罩不会缩成一条 */
.lablist-grid {
  min-height: 120px;
}

/* 每张卡下留间距（换行时行距） */
.lablist-col {
  margin-bottom: 16px;
}

/* 卡片本体：纯白大圆角 + 悬停浮起，封面缩放给出"可进入"的暗示 */
.lablist-item {
  overflow: hidden;
  background-color: #fff;
  border: 1px solid var(--color-border);
  border-radius: 14px;
  box-shadow: 0 1px 2px rgba(23, 35, 61, 0.04);
  transition: var(--transition-base);
}

.lablist-item:hover {
  border-color: rgba(79, 110, 247, 0.24);
  box-shadow: var(--shadow-card-hover);
  transform: translateY(-3px);
}

/* 内容区撑满卡片高度，配合 actions 的 margin-top:auto 让按钮对齐 */
.lablist-item :deep(.el-card__body) {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 14px 16px 18px;
}

.lablist-cover {
  display: block;
  width: 100%;
  height: 160px;
  overflow: hidden;
  border-radius: 10px;
}

/* 封面内的真实图片：悬停时缓慢放大，动效只作用在图片本身 */
.lablist-cover :deep(.el-image__inner) {
  transition: transform 0.45s cubic-bezier(0.22, 1, 0.36, 1);
}

.lablist-item:hover .lablist-cover :deep(.el-image__inner) {
  transform: scale(1.05);
}

.lablist-cover--empty {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: var(--color-text-muted);
  background: linear-gradient(135deg, #f2f5fd, #e9eefb);
}

.lablist-name {
  margin-top: 12px;
  overflow: hidden;
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lablist-meta {
  margin-top: 6px;
  font-size: 13px;
  color: var(--color-text-muted);
}

/* 按钮行与信息区用虚线分隔，多张卡并排时按钮仍钉在底部 */
.lablist-actions {
  display: flex;
  gap: 8px;
  padding-top: 14px;
  margin-top: auto;
  border-top: 1px dashed #eef2f8;
}

.lablist-actions .el-button {
  height: 36px;
  margin-left: 0;
  border-radius: 10px;
}

.lablist-pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
</style>
