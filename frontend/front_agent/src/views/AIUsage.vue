<script setup>
// AI 用量与花费（仅管理员）：从「AI模型配置」页拆出来的独立一页，只读不写
// 数据来自 GET /api/ai/usage/cost：后端按 能力+供应商+模型 聚合最近 N 天，
// 并用它自己的价格表算出每行 cost（价格表没有的模型 cost 为 null，不计入总花费）
import { computed, onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { getAiCostApi } from '@/api/ai'

// 能力 key → 中文名。与 AIConfig.vue 里那份是两份独立文案：
// 那页还要供应商候选和生成参数，这里只要标签，共用一个文件反而要把不相关的字段捆在一起
const CAPABILITY_LABELS = {
  chat: '聊天对话',
  chat_light: '轻量对话',
  vision: '视觉理解',
  ocr: 'OCR 识别',
  embedding: '融合向量',
  rerank: '重排序',
  intent: '意图识别',
  decision: '决策',
}
const PROVIDER_LABELS = { minimax: 'MiniMax', bailian: '百炼' }

// 条形图配色：同一色相族拉开深浅。不用纯红纯绿——那两个颜色在本项目里留给"危险/成功"语义
const PALETTE = [
  '#409eff',
  '#36a3a0',
  '#6c8ebf',
  '#9a86c8',
  '#d4a24c',
  '#7fa879',
  '#c98b8b',
  '#8a93a6',
]

const summary = ref(null) // 整个 data：{days, items, total_cost, priced_cost, currency, note}
const loading = ref(false)

const items = computed(() => summary.value?.items ?? [])
const currency = computed(() => summary.value?.currency || '元')

// token 数加千分位
const tokenText = (value) => Number(value ?? 0).toLocaleString()
// 花费保留 4 位小数：这个项目单次调用常在分以下，两位小数会全显示成 0.00
const moneyText = (value) =>
  value === null || value === undefined ? '-' : `${Number(value).toFixed(4)} ${currency.value}`
// 大数字用"万"缩写，卡片和条形图右侧才放得下：1587926 → 158.8万
function compactText(value) {
  const num = Number(value ?? 0)
  return num >= 10000 ? `${(num / 10000).toFixed(1)}万` : num.toLocaleString()
}

const totals = computed(() => {
  let tokens = 0
  let calls = 0
  let unpriced = 0
  let unpricedTokens = 0
  for (const item of items.value) {
    tokens += Number(item.total_tokens ?? 0)
    calls += Number(item.calls ?? 0)
    if (item.cost === null || item.cost === undefined) {
      unpriced += 1
      unpricedTokens += Number(item.total_tokens ?? 0)
    }
  }
  return { cost: summary.value?.total_cost ?? 0, tokens, calls, unpriced, unpricedTokens }
})

// 两张图共用同一个构造方式：条宽按"本组最大值"归一（最长的条顶满轨道，差异一眼看得出），
// 右侧百分比标的是"占总量份额"——那才是决定"该优化谁"的数字。
function buildChart(list, valueOf, formatValue) {
  const values = list.map((item) => Number(valueOf(item)) || 0)
  const max = Math.max(...values, 0.000001)
  const total = values.reduce((sum, value) => sum + value, 0) || 1
  return list.map((item, index) => ({
    key: `${item.capability}-${item.provider}-${item.model}`,
    label: `${CAPABILITY_LABELS[item.capability] ?? item.capability} · ${item.model}`,
    ratio: (values[index] / max) * 100,
    share: (values[index] / total) * 100,
    valueText: formatValue(values[index]),
    color: PALETTE[index % PALETTE.length],
  }))
}

// 花费图只画已计价的行：未计价的 cost 是 null，画进去会得到一条长度为 0 的误导条
const costChart = computed(() => {
  const priced = items.value
    .filter((item) => item.cost !== null && item.cost !== undefined)
    .sort((a, b) => (Number(b.cost) || 0) - (Number(a.cost) || 0))
  return buildChart(priced, (item) => item.cost, (value) => `${value.toFixed(4)} ${currency.value}`)
})

const tokenChart = computed(() => {
  const sorted = items.value
    .slice()
    .sort((a, b) => (Number(b.total_tokens) || 0) - (Number(a.total_tokens) || 0))
  return buildChart(sorted, (item) => item.total_tokens, compactText)
})

async function load() {
  loading.value = true
  try {
    const res = await getAiCostApi()
    if (res.code >= 200 && res.code < 300) {
      summary.value = res.data ?? null
    }
  } catch {
    // 提示归 request.js 拦截器
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="usage-card" v-loading="loading">
    <h3 class="usage-title">
      AI 用量与花费
      <el-button size="small" text :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
    </h3>

    <!-- 概览三卡：花了多少钱、烧了多少 token、调了多少次 -->
    <div class="usage-stats">
      <div class="usage-stat usage-stat--accent">
        <div class="usage-stat__label">最近 {{ summary?.days ?? 30 }} 天估算花费</div>
        <div class="usage-stat__value">{{ moneyText(totals.cost) }}</div>
        <div class="usage-stat__foot">已计价部分 {{ moneyText(summary?.priced_cost) }}</div>
      </div>
      <div class="usage-stat">
        <div class="usage-stat__label">总 token</div>
        <div class="usage-stat__value">{{ tokenText(totals.tokens) }}</div>
        <div class="usage-stat__foot">约 {{ compactText(totals.tokens) }} tokens</div>
      </div>
      <div class="usage-stat">
        <div class="usage-stat__label">总调用次数</div>
        <div class="usage-stat__value">{{ tokenText(totals.calls) }}</div>
        <div class="usage-stat__foot">{{ items.length }} 项能力/模型统计</div>
      </div>
    </div>

    <!-- note 必须展示：这是估算值，且 MiniMax 订阅是按等价 token 价值折算的 -->
    <el-alert v-if="summary?.note" type="warning" :closable="false" show-icon :title="summary.note" />
    <!-- 有未计价项时单独说一句，否则管理员会以为"总花费"就是全部成本 -->
    <el-alert
      v-if="totals.unpriced"
      type="info"
      :closable="false"
      show-icon
      :title="`另有 ${totals.unpriced} 项模型不在后端价格表内，未计入总花费（合计 ${tokenText(totals.unpricedTokens)} tokens）`"
    />

    <!-- 两张条形图：纯 CSS 画的。为一个页面引入图表库不值得，也没有外部请求依赖 -->
    <div class="usage-charts">
      <section class="usage-chart">
        <h4 class="usage-chart__title">花费构成</h4>
        <div v-for="row in costChart" :key="row.key" class="usage-bar">
          <div class="usage-bar__label" :title="row.label">{{ row.label }}</div>
          <div class="usage-bar__track">
            <span
              class="usage-bar__fill"
              :style="{ width: row.ratio + '%', backgroundColor: row.color }"
            />
          </div>
          <div class="usage-bar__value">
            {{ row.valueText }}<span class="usage-bar__share">{{ row.share.toFixed(1) }}%</span>
          </div>
        </div>
        <el-empty v-if="!costChart.length" :image-size="60" description="还没有已计价的使用量" />
      </section>

      <section class="usage-chart">
        <h4 class="usage-chart__title">Token 分布</h4>
        <div v-for="row in tokenChart" :key="row.key" class="usage-bar">
          <div class="usage-bar__label" :title="row.label">{{ row.label }}</div>
          <div class="usage-bar__track">
            <span
              class="usage-bar__fill"
              :style="{ width: row.ratio + '%', backgroundColor: row.color }"
            />
          </div>
          <div class="usage-bar__value">
            {{ row.valueText }}<span class="usage-bar__share">{{ row.share.toFixed(1) }}%</span>
          </div>
        </div>
        <el-empty v-if="!tokenChart.length" :image-size="60" description="还没有调用记录" />
      </section>
    </div>

    <!-- 明细表：图看趋势，表看准确数字 -->
    <el-table v-if="items.length" class="usage-table" :data="items" style="width: 100%">
      <el-table-column label="能力" width="130">
        <template #default="{ row }">
          {{ CAPABILITY_LABELS[row.capability] ?? row.capability }}
        </template>
      </el-table-column>
      <el-table-column label="供应商" width="110">
        <template #default="{ row }">{{ PROVIDER_LABELS[row.provider] || row.provider }}</template>
      </el-table-column>
      <el-table-column prop="model" label="模型" min-width="190">
        <template #default="{ row }">
          <span class="usage-ellipsis" :title="row.model">{{ row.model || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="calls" label="调用次数" width="100" />
      <el-table-column label="输入 token" width="120">
        <template #default="{ row }">{{ tokenText(row.input_tokens) }}</template>
      </el-table-column>
      <el-table-column label="输出 token" width="120">
        <template #default="{ row }">{{ tokenText(row.output_tokens) }}</template>
      </el-table-column>
      <el-table-column label="合计 token" width="120">
        <template #default="{ row }">{{ tokenText(row.total_tokens) }}</template>
      </el-table-column>
      <el-table-column label="估算花费" width="140">
        <template #default="{ row }">
          <!-- cost 为 null = 后端价格表里没有这个模型，没算进总花费，必须标出来 -->
          <span v-if="row.cost !== null && row.cost !== undefined">{{ moneyText(row.cost) }}</span>
          <el-tag v-else size="small" type="info">未计价</el-tag>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-else-if="!loading" description="最近 30 天还没有调用记录" />
  </div>
</template>

<style scoped>
/* 外壳：manager 子页面族同款玻璃卡 */
.usage-card {
  padding: 24px;
  background-color: var(--color-surface-glass);
  backdrop-filter: blur(12px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}

.usage-title {
  display: flex;
  gap: 12px;
  align-items: center;
  margin: 0 0 16px;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
}

/* 概览卡：窄屏自动折成一列 */
.usage-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.usage-stat {
  padding: 14px 18px;
  background-color: rgba(255, 255, 255, 0.6);
  border: 1px solid var(--color-border);
  border-radius: 10px;
}

/* 只有"花了多少钱"这张用强调底色，其余保持中性，避免三块都在抢视线 */
.usage-stat--accent {
  background: var(--gradient-accent-soft, rgba(64, 158, 255, 0.1));
  border-color: rgba(64, 158, 255, 0.35);
}

.usage-stat__label {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.usage-stat__value {
  margin: 4px 0 2px;
  font-size: 26px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.usage-stat__foot {
  font-size: 12px;
  color: var(--color-text-muted);
}

.usage-card :deep(.el-alert) {
  margin-bottom: 12px;
}

/* 两张图并排；窄屏自动上下堆叠 */
.usage-charts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
  margin: 16px 0 20px;
}

.usage-chart {
  padding: 14px 16px;
  background-color: rgba(255, 255, 255, 0.5);
  border: 1px solid var(--color-border);
  border-radius: 10px;
}

.usage-chart__title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

/* 条形图三列：标签 | 轨道 | 数值 */
.usage-bar {
  display: grid;
  grid-template-columns: minmax(110px, 170px) 1fr auto;
  gap: 10px;
  align-items: center;
  margin-bottom: 8px;
}

.usage-bar__label {
  overflow: hidden;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text-secondary);
}

.usage-bar__track {
  height: 10px;
  overflow: hidden;
  background-color: rgba(0, 21, 41, 0.07);
  border-radius: 6px;
}

.usage-bar__fill {
  display: block;
  height: 100%;
  border-radius: 6px;
  /* 刷新数据时宽度有个过渡，不至于跳变 */
  transition: width 0.4s ease;
}

.usage-bar__value {
  min-width: 92px;
  font-size: 12px;
  text-align: right;
  color: var(--color-text-primary);
}

.usage-bar__share {
  margin-left: 6px;
  color: var(--color-text-muted);
}

/* 表格透明化：与其它页同款 */
.usage-table {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(245, 247, 250, 0.7);
}

.usage-ellipsis {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
