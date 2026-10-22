<script setup>
// AI 供应商配置管理（仅管理员）：8 个能力各自选供应商 / 填 key / 查模型 / 调生成参数 / 启用
// 与知识库页的"异步任务"视角不同，这页是纯同步的读—改—写：
//   GET /api/ai/admin/configs 读列表 → 弹窗里 POST /api/ai/provider/models 查模型 → PUT 保存
// 密钥永远只以脱敏串（sk-ab****cd）显示；保存时留空 = 后端保留原密钥。
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { getAiConfigListApi, getProviderModelsApi, saveAiConfigApi } from '@/api/ai'

// ===== 前端只保存展示文案；能力允许哪些供应商由后端 allowed_providers 返回 =====
// 兼容矩阵属于后端业务规则，不能只靠浏览器下拉框限制。
const CAPABILITIES = [
  { key: 'chat', label: '聊天对话', desc: '回答用户提问' },
  {
    key: 'chat_light',
    label: '轻量对话',
    desc: '闲聊走这里；未配置时自动回退到「聊天对话」',
  },
  { key: 'vision', label: '视觉理解', desc: '文档解析与图片描述' },
  { key: 'ocr', label: 'OCR 识别', desc: '扫描件与铭牌文字' },
  { key: 'embedding', label: '融合向量', desc: '知识库向量化（百炼专有）' },
  { key: 'rerank', label: '重排序', desc: '召回结果精排' },
  {
    key: 'intent',
    label: '意图识别',
    desc: '检索前判断要不要查知识库、开哪些工具',
  },
  {
    key: 'decision',
    label: '决策',
    desc: '生成预约草稿前核验参数是否由用户明确给出',
  },
]

// 能力 key → 文案项，模板里按 row.capability 反查
const capabilityMap = Object.fromEntries(CAPABILITIES.map((item) => [item.key, item]))
const PROVIDER_LABELS = { minimax: 'MiniMax', bailian: '百炼' }

// 思考层级候选值：保存到管理员能力配置中（MiniMax 不支持 none 关闭思考）
const REASONING_OPTIONS = [
  { value: 'low', label: 'low' },
  { value: 'medium', label: 'medium' },
  { value: 'high', label: 'high' },
  { value: 'xhigh', label: 'xhigh' },
  { value: 'max', label: 'max' },
]

const configs = ref([])
const loading = ref(false)

// ===== 编辑弹窗状态 =====
const dialogVisible = ref(false)
const saving = ref(false)
const querying = ref(false)
// 查询回来的模型列表（未查询时为空数组）
const modelOptions = ref([])
const formRef = ref(null)
// 用于判断管理员是否正在切换供应商；切换时旧供应商的密钥不能被静默复用。
const originalProvider = ref('')
// 字段名与后端 ProviderConfigUpsertRequest 完全一致（snake_case），保存时不用翻译
const form = reactive({
  capability: '',
  provider: '',
  model: '',
  base_url: '',
  api_key: '', // 空串 = 不修改原密钥
  // 百炼专有的 DashScope 根地址（模型列表/embedding/rerank 走 /api/v1，与 OpenAI 兼容地址不同）。
  // 后端语义：null = 保持原值、空串 = 清空、非空 = 覆盖。表单里始终送字符串，
  // 所以"打开没改"就是原值回写，不会像 timeout_seconds 那样被无意清掉。
  dashscope_base_url: '',
  reasoning_effort: null,
  timeout_seconds: null, // null = 用后端全局默认超时
  // 生成参数：null/空 = 沿用代码默认，不向供应商传该参数
  temperature: null,
  top_p: null,
  max_output_tokens: null,
  system_prompt: '',
  // 模型上下文窗口：查询模型时由下拉项自动带过来，存库后聊天页才能画上下文进度条
  context_window: null,
  is_active: true,
})

const rules = {
  // 每一项都必须有 prop，否则 el-form 的校验和 resetFields 会静默跳过它（本项目踩过）
  provider: [{ required: true, message: '请选择供应商', trigger: 'change' }],
  base_url: [{ required: true, message: '请填写 Base URL', trigger: 'blur' }],
  model: [{ required: true, message: '请选择或填写模型', trigger: 'change' }],
}

// 后端返回的当前能力配置；供应商候选也从这里读取，避免前后端规则漂移。
const currentConfig = computed(() =>
  configs.value.find((item) => item.capability === form.capability)
)
const providerOptions = computed(() =>
  (currentConfig.value?.allowed_providers ?? []).map((value) => ({
    value,
    label: PROVIDER_LABELS[value] ?? value,
  }))
)
// 只有"查询过模型且选中项 reasoning=true"才显示思考层级——没查询时不凭空冒出一个字段。
// 另外只有 chat / chat_light 两条链路会真的把 reasoning_effort 传给供应商，
// 视觉/OCR/向量/意图/决策都不看它，所以别的能力不显示，免得配了没效果。
const REASONING_CAPABILITIES = ['chat', 'chat_light']
const selectedModel = computed(() => modelOptions.value.find((m) => m.id === form.model) ?? null)
const showReasoning = computed(
  () => REASONING_CAPABILITIES.includes(form.capability) && Boolean(selectedModel.value?.reasoning)
)
// 温度/top_p/输出上限/系统提示词目前只有 chat 与 chat_light 生效（其余能力在代码里
// 用的是固定参数），所以只对这两个能力显示，避免管理员配了却没作用。
const showGenerationParams = computed(() => REASONING_CAPABILITIES.includes(form.capability))
// 窗口大小按 k 显示，32768 → 32k，方便一眼比较
const windowText = (size) => (size ? `${Math.round(size / 1024)}k` : '-')

// 密钥输入框的占位文案：已配置就把脱敏串显示出来，管理员一眼知道"留空=不改"
const keyPlaceholder = computed(() => {
  const canReuseKey = currentConfig.value?.has_key && form.provider === originalProvider.value
  return canReuseKey
    ? `当前 ${currentConfig.value.api_key_masked}，留空则不修改`
    : '填写该供应商的 API Key'
})

// 复刻后端 resolve_dashscope_base 的规则：DashScope 地址留空时，百炼的
// 模型列表 / embedding / rerank 会打到这个派生地址上。把预览显示出来，
// 管理员才能看出"派生出来的地址根本不对"——这类 401/404 光看报错文案查不出来。
const derivedDashscope = computed(() => {
  const base = (form.base_url || '').trim().replace(/\/+$/, '')
  if (!base) return ''
  const suffix = '/compatible-mode/v1'
  if (base.endsWith(suffix)) return `${base.slice(0, -suffix.length)}/api/v1`
  return base
})

// 后端对"从没配置过的能力"返回占位行（provider/model/base_url 全空串、is_active=false）。
// 这种行显示"已停用"会让人以为有人关过它，所以单独判成"未配置"。
const isUnconfigured = (row) => !row.provider && !row.model && !row.has_key

async function loadConfigs() {
  loading.value = true
  try {
    const res = await getAiConfigListApi()
    if (res.code >= 200 && res.code < 300) {
      configs.value = res.data ?? []
    }
  } catch {
    // 提示归 request.js 拦截器
  } finally {
    loading.value = false
  }
}

// 打开弹窗：从后端视图回填，密钥不进表单（只有脱敏串可显示）
function openEdit(row) {
  modelOptions.value = []
  originalProvider.value = row.provider || ''
  Object.assign(form, {
    capability: row.capability,
    // 未配置时默认落在"该能力允许的第一个供应商"，而不是前端硬偏爱某一家
    provider: row.provider || row.allowed_providers?.[0] || '',
    model: row.model,
    base_url: row.base_url,
    api_key: '',
    dashscope_base_url: row.dashscope_base_url ?? '',
    reasoning_effort: row.reasoning_effort ?? null,
    timeout_seconds: row.timeout_seconds ?? null,
    temperature: row.temperature ?? null,
    top_p: row.top_p ?? null,
    max_output_tokens: row.max_output_tokens ?? null,
    system_prompt: row.system_prompt ?? '',
    context_window: row.context_window ?? null,
    is_active: row.is_active,
  })
  dialogVisible.value = true
  formRef.value?.clearValidate()
}

// 切换供应商时清理所有与旧供应商绑定的字段。尤其不能保留旧 Key：
// 后端也会再次校验，防止绕过前端直接调用接口。
function handleProviderChange() {
  modelOptions.value = []
  form.model = ''
  form.base_url = ''
  form.api_key = ''
  form.dashscope_base_url = ''
  form.reasoning_effort = null
  form.context_window = null
}

// 查询模型：这一步要出网访问 MiniMax/百炼，key 错就 4xx，不保存任何东西
async function handleQueryModels() {
  if (!form.provider || !form.base_url.trim() || !form.api_key.trim()) {
    ElMessage.warning('请先填供应商、Base URL 和 API Key')
    return
  }
  querying.value = true
  try {
    const res = await getProviderModelsApi({
      provider: form.provider,
      base_url: form.base_url.trim(),
      api_key: form.api_key.trim(),
      // 百炼官方返回的是混合能力模型列表；把当前配置项的能力交给后端，
      // 由供应商适配器映射成 TG/VU/ME 或 OCR/Rerank 模型筛选规则。
      capability: form.capability,
    })
    if (res.code >= 200 && res.code < 300) {
      modelOptions.value = res.data ?? []
      if (!modelOptions.value.length) {
        ElMessage.warning('这个 key 没有查到可用模型')
        return
      }
      // 原来的模型不在新列表里就清掉，避免"保存了一个供应商根本没有的模型"
      if (!modelOptions.value.some((m) => m.id === form.model)) {
        form.model = modelOptions.value.find((m) => m.is_default)?.id ?? modelOptions.value[0].id
        form.reasoning_effort = null
      }
      ElMessage.success(`查到 ${modelOptions.value.length} 个模型`)
    }
  } catch {
    // 提示归拦截器
  } finally {
    querying.value = false
  }
}

async function handleSave() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  if (form.provider !== originalProvider.value && !form.api_key.trim()) {
    ElMessage.warning('切换供应商时必须填写新供应商的 API Key')
    return
  }
  saving.value = true
  try {
    const res = await saveAiConfigApi(form.capability, {
      provider: form.provider,
      model: form.model,
      base_url: form.base_url.trim(),
      // 空串归一成 null：语义是"保留原密钥"，别让后端收到空串再猜
      api_key: form.api_key.trim() || null,
      // 后端语义：null=保持原值、空串=清空、非空=覆盖。表单永远送字符串，
      // 且 openEdit 已用原值预填，所以"没改过"就是原值回写，不会被清空。
      dashscope_base_url: form.dashscope_base_url.trim(),
      reasoning_effort: form.reasoning_effort || null,
      // 后端是整条覆盖（row.timeout_seconds = data.timeout_seconds），
      // 这个字段必须一起回传，否则保存一次就把管理员设过的超时清成 null
      timeout_seconds: form.timeout_seconds ?? null,
      // 只有 chat / chat_light 会用到这四项；其它能力一律送 null，
      // 免得在数据库里留下"配了但没人读"的值。
      temperature: showGenerationParams.value ? (form.temperature ?? null) : null,
      top_p: showGenerationParams.value ? (form.top_p ?? null) : null,
      max_output_tokens: showGenerationParams.value ? (form.max_output_tokens ?? null) : null,
      system_prompt: showGenerationParams.value ? form.system_prompt.trim() || null : null,
      // 查询过模型就带上选中项的窗口；没查询则保留原值，避免保存一次把窗口清空
      context_window: selectedModel.value?.context_window ?? form.context_window ?? null,
      is_active: form.is_active,
    })
    if (res.code >= 200 && res.code < 300) {
      ElMessage.success(res.message || '保存成功！')
      dialogVisible.value = false
      loadConfigs() // 重新拉列表：脱敏串和启用状态都由后端说了算，不在本地拼
    }
  } catch {
    // 提示归拦截器
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadConfigs()
})
</script>

<template>
  <div class="cfg-card">
    <h3 class="cfg-title">AI 模型配置</h3>

    <!-- 能力配置表：能力行固定由后端返回，前端不额外造行 -->
    <el-table v-loading="loading" :data="configs" style="width: 100%">
      <el-table-column label="能力" width="150">
        <template #default="{ row }">
          <div class="cfg-cap">
            <span>{{ capabilityMap[row.capability]?.label ?? row.capability }}</span>
            <span class="cfg-cap__key">{{ row.capability }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="供应商" width="100">
        <template #default="{ row }">{{ PROVIDER_LABELS[row.provider] || '未配置' }}</template>
      </el-table-column>
      <el-table-column label="模型" min-width="200">
        <template #default="{ row }">
          <span class="cfg-ellipsis" :title="row.model">{{ row.model || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="Base URL" min-width="220">
        <template #default="{ row }">
          <span class="cfg-ellipsis cfg-ellipsis--wide" :title="row.base_url">
            {{ row.base_url || '-' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="密钥" width="150">
        <template #default="{ row }">
          <!-- 后端只给脱敏串；没配过就是 '-'（"未配置"由状态列统一表达，不重复两遍） -->
          <span v-if="row.has_key" class="cfg-key">{{ row.api_key_masked }}</span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="超时" width="90">
        <template #default="{ row }">
          <!-- null 表示没单独设过，走后端全局超时（BAILIAN_TIMEOUT_SECONDS） -->
          {{ row.timeout_seconds ? `${row.timeout_seconds} 秒` : '默认' }}
        </template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag v-if="isUnconfigured(row)" size="small" type="info">未配置</el-tag>
          <el-tag v-else :type="row.is_active ? 'success' : 'warning'" size="small">
            {{ row.is_active ? '已启用' : '已停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="90">
        <template #default="{ row }">
          <el-button
            size="small"
            text
            bg
            @click="openEdit(row)"
          >
            配置
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 编辑弹窗：append-to-body 必须加，否则被 .cfg-card 的 backdrop-filter 抢走 fixed 定位 -->
    <el-dialog
      v-model="dialogVisible"
      :title="`配置 ${capabilityMap[form.capability]?.label ?? form.capability}`"
      width="560px"
      append-to-body
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="92px">
        <el-form-item label="供应商" prop="provider">
          <el-select v-model="form.provider" class="cfg-full" @change="handleProviderChange">
            <el-option
              v-for="item in providerOptions"
              :key="item.value"
              :value="item.value"
              :label="item.label"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="Base URL" prop="base_url">
          <el-input v-model="form.base_url" placeholder="https://api.minimax.cn/v1" maxlength="300" />
        </el-form-item>

        <!-- DashScope 根地址只对百炼有意义：模型列表 / embedding / rerank 走 /api/v1，
             和 OpenAI 兼容地址不是同一个入口。MiniMax 没有这个概念，所以选它时不显示。 -->
        <el-form-item v-if="form.provider === 'bailian'" label="DashScope">
          <el-input
            v-model="form.dashscope_base_url"
            maxlength="300"
            :placeholder="derivedDashscope || '留空则按 Base URL 自动派生'"
          />
          <div class="cfg-hint cfg-hint--block">
            <template v-if="form.dashscope_base_url.trim()">
              实际请求：<code>{{ form.dashscope_base_url.trim().replace(/\/+$/, '') }}/models</code>
            </template>
            <template v-else-if="derivedDashscope">
              留空时按 Base URL 派生，实际请求：<code>{{ derivedDashscope }}/models</code>
              <br />
              派生结果不对（地域、工作空间、网关路径不一致）就在这里手填正确的
              <code>.../api/v1</code> 根地址
            </template>
            <template v-else>先填 Base URL，这里会显示派生出的实际请求地址</template>
          </div>
        </el-form-item>

        <el-form-item label="API Key">
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            maxlength="500"
            :placeholder="keyPlaceholder"
          />
        </el-form-item>

        <el-form-item label="模型" prop="model">
          <div class="cfg-model-row">
            <el-select
              v-model="form.model"
              class="cfg-full"
              filterable
              placeholder="先查一次，或直接保留当前模型"
            >
              <!-- 没查询过时，至少把当前值显示成一个选项，否则下拉里是空的 -->
              <el-option
                v-if="!modelOptions.length && form.model"
                :value="form.model"
                :label="`${form.model}（未查询，保存原值）`"
              />
              <el-option
                v-for="item in modelOptions"
                :key="item.id"
                :value="item.id"
                :label="`${item.name || item.id} · ${windowText(item.context_window)}${
                  item.vision ? ' · 支持图片' : ''
                }${item.is_default ? ' · 默认' : ''}`"
              />
            </el-select>
            <el-button :icon="Search" :loading="querying" @click="handleQueryModels">
              查询模型
            </el-button>
          </div>
        </el-form-item>

        <!-- 只有查到的模型确实支持思考参数，才出现这一项 -->
        <el-form-item v-if="showReasoning" label="思考层级">
          <el-select v-model="form.reasoning_effort" class="cfg-full" clearable placeholder="不设置">
            <el-option
              v-for="item in REASONING_OPTIONS"
              :key="item.value"
              :value="item.value"
              :label="item.label"
            />
          </el-select>
        </el-form-item>

        <!-- 单次外部请求的等待秒数；清空 = 不单独设，回后端全局默认 -->
        <el-form-item label="请求超时">
          <el-input-number
            v-model="form.timeout_seconds"
            :min="1"
            :max="300"
            :step="10"
            :value-on-clear="null"
            placeholder="默认"
          />
          <span class="cfg-hint">1–300 秒，留空用后端全局默认</span>
        </el-form-item>

        <!-- 生成参数：只有 chat / chat_light 会真正传给供应商，其它能力不显示 -->
        <template v-if="showGenerationParams">
          <el-form-item label="温度">
            <el-input-number
              v-model="form.temperature"
              :min="0"
              :max="2"
              :step="0.1"
              :precision="2"
              :value-on-clear="null"
              placeholder="默认"
            />
            <span class="cfg-hint">0–2，越大越发散；留空用供应商默认</span>
          </el-form-item>

          <el-form-item label="Top P">
            <el-input-number
              v-model="form.top_p"
              :min="0"
              :max="1"
              :step="0.05"
              :precision="2"
              :value-on-clear="null"
              placeholder="默认"
            />
            <span class="cfg-hint">0–1，核采样；留空用供应商默认</span>
          </el-form-item>

          <el-form-item label="输出上限">
            <el-input-number
              v-model="form.max_output_tokens"
              :min="1"
              :max="131072"
              :step="512"
              :value-on-clear="null"
              placeholder="默认"
            />
            <span class="cfg-hint">单次回答的 token 上限，留空用全局默认</span>
          </el-form-item>

          <el-form-item label="系统提示词">
            <el-input
              v-model="form.system_prompt"
              type="textarea"
              :rows="6"
              maxlength="20000"
              show-word-limit
              placeholder="留空使用内置提示词；填写后覆盖"
            />
          </el-form-item>
        </template>

        <el-form-item label="启用">
          <el-switch v-model="form.is_active" />
          <span class="cfg-hint">关闭后视为未配置：该能力不可用，相关功能走各自的降级逻辑</span>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
/* 外壳：manager 子页面族同款玻璃卡 */
.cfg-card {
  padding: 24px;
  background-color: var(--color-surface-glass);
  backdrop-filter: blur(12px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}

.cfg-title {
  margin: 0 0 16px;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
}

/* 表格透明化：与其它页同款 */
.cfg-card :deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(245, 247, 250, 0.7);
}

.cfg-cap {
  display: flex;
  flex-direction: column;
}

.cfg-cap__key {
  font-size: 12px;
  color: var(--color-text-muted);
}

/* 模型名与 URL：单行截断 + 原生 title（不用 show-overflow-tooltip，本项目已确认会错位） */
.cfg-ellipsis {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cfg-ellipsis--wide {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.cfg-key {
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
}

/* 弹窗里撑满整行的控件 */
.cfg-full {
  width: 100%;
}

.cfg-model-row {
  display: flex;
  gap: 8px;
  width: 100%;
}

.cfg-hint {
  margin-left: 10px;
  font-size: 12px;
  color: var(--color-text-muted);
}

/* 需要独占一行的提示（派生地址预览）；行内版留给紧跟控件的那种 */
.cfg-hint--block {
  margin-left: 0;
  line-height: 1.6;
}

.cfg-hint code {
  padding: 0 4px;
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  word-break: break-all;
  background-color: rgba(0, 21, 41, 0.06);
  border-radius: 3px;
}
</style>
