<script setup>
// 系统首页（教程26）：欢迎区 + 统计 + 能力说明 + 快捷入口
// 关键点：统计不新开"首页专用接口"，直接复用已有分页接口，只要它的 total
//   （page_size 给 1，只取一条数据换取总数，浪费最小）。
// 任何一个统计失败都只让那一张卡显示 "-"，不能把整个首页带崩。
import { computed, onMounted, ref } from 'vue'
// useRouter：快捷入口用程序化导航（模板里也能直接写 $router.push，这里统一走 setup 里的实例）
import { useRouter } from 'vue-router'
import { ChatDotRound, Right } from '@element-plus/icons-vue'
// 登录态：userInfo 是 utils/user.js 的模块级 ref，登录后一直有值
import { useUser } from '@/utils/user'
import { getKnowledgePageListApi } from '@/api/knowledge'
import { getLabPageListApi } from '@/api/lab'
import { getReservationPageListApi } from '@/api/reservation'

const { userInfo } = useUser()
const router = useRouter()

// 角色判断只写这一处：统计项、卡片文案、快捷入口都跟着它走，避免三个地方各判一遍
const isAdmin = computed(() => userInfo.value?.role === 'admin')
const roleLabel = computed(() => (isAdmin.value ? '管理员' : '学生'))

// '-' 是"还没拿到/拿不到"的初始态，而不是 0 —— 0 是一个真实的业务数字，不能拿来当占位
const labTotal = ref('-')
const reservationTotal = ref('-')
const knowledgeTotal = ref('-')

// 预约这一张卡对两种角色含义不同：后端 list 接口对学生返回本人预约、
// 对管理员返回全部预约，所以标题必须跟着角色变，否则管理员会以为看到的是自己的量
const reservationLabel = computed(() => (isAdmin.value ? '全部预约' : '我的预约'))

const statCards = computed(() => {
  const list = [
    {
      label: '开放实验室',
      value: labTotal.value,
      foot: '状态为开放、可被预约的实验室',
    },
    {
      label: reservationLabel.value,
      value: reservationTotal.value,
      foot: isAdmin.value ? '需要处理的预约总量' : '你提交过的预约总量',
    },
  ]
  // 知识库接口是管理员专属，学生调会 403 —— 所以连请求都不发，卡片也不显示
  if (isAdmin.value) {
    list.push({ label: '知识库文档', value: knowledgeTotal.value, foot: '已上传并完成处理的文档' })
  }
  return list
})

// 能力说明：写死的前端文案，只描述"系统已经具备的能力"，不写没做的
const features = [
  {
    title: '业务预约',
    desc: '浏览实验室与设备、提交预约、查看我的预约；管理员在预约审核里通过或拒绝。',
  },
  {
    title: '知识库问答',
    desc: '上传 DOCX/PDF/Excel/Markdown 等文档，自动解析、切块、向量化；回答规则与开放时间时有据可依。',
  },
  {
    title: '智能 Agent',
    desc: 'Tool Calling 查实时数据库，流式输出过程可见；预约只生成草稿，你点确认才真正提交。',
  },
]

// 快捷入口与侧边栏菜单保持同一套角色规则：菜单里看不到的页面，首页也不给入口，
// 免得出现"菜单说你没有这个功能、首页却有按钮"的自相矛盾
const shortcuts = computed(() => {
  const common = [{ label: 'AI 智能助手', path: '/manager/aichat' }]
  if (isAdmin.value) {
    return [
      ...common,
      { label: '预约审核', path: '/manager/auditreservation' },
      { label: '实验室管理', path: '/manager/lab' },
      { label: '设备管理', path: '/manager/equipment' },
      { label: '用户管理', path: '/manager/users' },
      { label: '知识库管理', path: '/manager/knowledge' },
      { label: 'AI模型配置', path: '/manager/aiconfig' },
      { label: 'AI用量花费', path: '/manager/aiusage' },
    ]
  }
  return [
    ...common,
    { label: '实验室列表', path: '/manager/lablist' },
    { label: '我的预约', path: '/manager/myreservation' },
  ]
})

// 一个分页请求 → 只要 total；失败或业务码非 2xx 都归一成 '-'
// 错误提示已经由 request.js 拦截器统一弹过，这里不再重复提示
async function safeTotal(promise) {
  try {
    const res = await promise
    if (res.code >= 200 && res.code < 300) return res.data?.total ?? 0
    return '-'
  } catch {
    return '-'
  }
}

async function loadStats() {
  // Promise.all 并发发出：三个请求互不依赖，串行会让首页白屏时间变成三倍
  const [labs, reservations, knowledge] = await Promise.all([
    // status=1 只对管理员有意义（非管理员后端强制只查开放状态），传了也不冲突
    safeTotal(getLabPageListApi({ page: 1, page_size: 1, status: 1 })),
    safeTotal(getReservationPageListApi({ page: 1, page_size: 1 })),
    isAdmin.value ? safeTotal(getKnowledgePageListApi({ page: 1, page_size: 1 })) : null,
  ])
  labTotal.value = labs
  reservationTotal.value = reservations
  if (knowledge !== null) knowledgeTotal.value = knowledge
}

onMounted(loadStats)
</script>

<template>
  <div class="home">
    <!-- ===== 欢迎区 ===== -->
    <section class="home-hero">
      <div class="home-hero__text">
        <h2 class="home-hero__title">你好，{{ userInfo?.name || '同学' }}</h2>
        <p class="home-hero__desc">
          欢迎使用 AI 智能实验室预约系统 · 当前身份：{{ roleLabel }}
        </p>
      </div>
      <el-button type="primary" :icon="ChatDotRound" @click="router.push('/manager/aichat')">
        打开 AI 助手
      </el-button>
    </section>

    <!-- ===== 统计卡：窄屏自动折行，不依赖 el-row 的断点 ===== -->
    <section class="home-stats">
      <div v-for="item in statCards" :key="item.label" class="home-stat">
        <div class="home-stat__label">{{ item.label }}</div>
        <div class="home-stat__value">{{ item.value }}</div>
        <div class="home-stat__foot">{{ item.foot }}</div>
      </div>
    </section>

    <!-- ===== 能力说明 ===== -->
    <section class="home-block">
      <h3 class="home-block__title">系统能做什么</h3>
      <div class="home-features">
        <div v-for="item in features" :key="item.title" class="home-feature">
          <div class="home-feature__title">{{ item.title }}</div>
          <p class="home-feature__desc">{{ item.desc }}</p>
        </div>
      </div>
    </section>

    <!-- ===== 快捷入口 ===== -->
    <section class="home-block">
      <h3 class="home-block__title">快捷入口</h3>
      <div class="home-shortcuts">
        <!-- 图标放文字右侧要用官方这个写法：el-button 没有"图标位置"这个 prop，
             :icon 只能把图标放在左边 -->
        <el-button
          v-for="item in shortcuts"
          :key="item.path"
          @click="router.push(item.path)"
        >
          {{ item.label }}
          <el-icon class="el-icon--right"><Right /></el-icon>
        </el-button>
      </div>
    </section>
  </div>
</template>

<style scoped>
/* 首页：品牌渐变 Hero + 彩色统计卡 + 编号能力卡 + 卡片化快捷入口 */
.home {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

/* ===== Hero：深色品牌渐变块，给浅色页面一个视觉锚点 ===== */
.home-hero {
  position: relative;
  display: flex;
  gap: 20px;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  padding: 32px 36px;
  overflow: hidden;
  color: #fff;
  background: linear-gradient(120deg, #2f3b8f 0%, #4f46e5 46%, #7c3aed 100%);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 20px;
  box-shadow: 0 26px 60px -30px rgba(79, 70, 229, 0.65);
}

/* 两团柔光：右上白色高光 + 右下青色光晕，制造"资源站头图"的层次 */
.home-hero::before {
  content: '';
  position: absolute;
  top: -90px;
  right: -60px;
  width: 280px;
  height: 280px;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.28), transparent 65%);
  border-radius: 50%;
}

.home-hero::after {
  content: '';
  position: absolute;
  bottom: -130px;
  left: 42%;
  width: 340px;
  height: 340px;
  pointer-events: none;
  background: radial-gradient(circle, rgba(6, 182, 212, 0.35), transparent 65%);
  border-radius: 50%;
}

.home-hero__text {
  position: relative;
  z-index: 1;
}

.home-hero__title {
  margin: 0;
  font-size: 30px;
  font-weight: 800;
  letter-spacing: 0.01em;
  color: #fff;
}

.home-hero__desc {
  margin: 10px 0 0;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.78);
}

/* Hero 里的按钮反转为白底品牌字，避免整块都是紫色系
   主按钮的全局渐变选择器权重更高，这里用 !important 锁死白底与字色 */
.home-hero .el-button.el-button--primary {
  position: relative;
  z-index: 1;
  height: 42px;
  padding: 0 20px;
  font-weight: 600;
  color: #4f46e5 !important;
  background: #fff !important;
  border: none;
  border-radius: 12px;
  box-shadow: 0 12px 28px -12px rgba(0, 0, 0, 0.45);
}

.home-hero .el-button.el-button--primary:hover {
  color: #4338ca !important;
  background: #fff !important;
  filter: none;
  box-shadow: 0 16px 32px -12px rgba(0, 0, 0, 0.5);
  transform: translateY(-2px);
}

/* ===== 统计卡：白卡 + 顶部彩色条 + 渐变数字 ===== */
.home-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 16px;
}

.home-stat {
  position: relative;
  padding: 20px 22px 18px;
  overflow: hidden;
  background-color: #fff;
  border: 1px solid var(--color-border);
  border-radius: 16px;
  box-shadow: var(--shadow-card);
  transition: var(--transition-base);
}

.home-stat::before {
  content: '';
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  height: 4px;
  background: var(--gradient-accent);
}

.home-stat::after {
  content: '';
  position: absolute;
  right: -46px;
  bottom: -56px;
  width: 130px;
  height: 130px;
  pointer-events: none;
  background: radial-gradient(circle, rgba(79, 110, 247, 0.12), transparent 68%);
  border-radius: 50%;
}

.home-stat:nth-child(2)::before {
  background: var(--gradient-cyan);
}

.home-stat:nth-child(2)::after {
  background: radial-gradient(circle, rgba(6, 182, 212, 0.14), transparent 68%);
}

.home-stat:nth-child(3)::before {
  background: var(--gradient-warm);
}

.home-stat:nth-child(3)::after {
  background: radial-gradient(circle, rgba(245, 158, 11, 0.16), transparent 68%);
}

.home-stat:hover {
  border-color: rgba(79, 110, 247, 0.24);
  box-shadow: var(--shadow-card-hover);
  transform: translateY(-3px);
}

.home-stat__label {
  position: relative;
  z-index: 1;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-secondary);
}

.home-stat__value {
  position: relative;
  z-index: 1;
  margin: 8px 0 4px;
  font-size: 34px;
  font-weight: 800;
  line-height: 1.1;
  letter-spacing: -0.02em;
  background: var(--gradient-accent);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.home-stat:nth-child(2) .home-stat__value {
  background: var(--gradient-cyan);
  -webkit-background-clip: text;
  background-clip: text;
}

.home-stat:nth-child(3) .home-stat__value {
  background: var(--gradient-warm);
  -webkit-background-clip: text;
  background-clip: text;
}

.home-stat__foot {
  position: relative;
  z-index: 1;
  font-size: 12px;
  color: var(--color-text-muted);
}

/* ===== 内容块：统一白卡 ===== */
.home-block {
  padding: 22px 24px 24px;
  background-color: #fff;
  border: 1px solid var(--color-border);
  border-radius: 16px;
  box-shadow: var(--shadow-card);
}

.home-block__title {
  margin: 0 0 16px;
  font-size: 16px;
}

/* ===== 能力卡：浅底 + 渐变编号徽章 ===== */
.home-features {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 14px;
  counter-reset: feature;
}

.home-feature {
  counter-increment: feature;
  padding: 16px 16px 16px 18px;
  background-color: var(--color-surface-soft);
  border: 1px solid #edf1f9;
  border-radius: 14px;
  transition: var(--transition-base);
}

.home-feature::before {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  margin-bottom: 12px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--color-accent);
  content: '0' counter(feature);
  background: var(--gradient-accent-soft);
  border-radius: 10px;
}

.home-feature:nth-child(2)::before {
  color: #0891b2;
  background: linear-gradient(135deg, rgba(6, 182, 212, 0.16), rgba(59, 130, 246, 0.1));
}

.home-feature:nth-child(3)::before {
  color: #d97706;
  background: linear-gradient(135deg, rgba(245, 158, 11, 0.18), rgba(249, 115, 22, 0.1));
}

.home-feature:hover {
  background-color: #fff;
  border-color: rgba(79, 110, 247, 0.22);
  box-shadow: 0 14px 28px -18px rgba(79, 110, 247, 0.35);
  transform: translateY(-2px);
}

.home-feature__title {
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text-primary);
}

.home-feature__desc {
  margin: 8px 0 0;
  font-size: 13px;
  line-height: 1.75;
  color: var(--color-text-secondary);
}

/* ===== 快捷入口：从一排"默认按钮"变成一排可悬停的入口卡 ===== */
.home-shortcuts {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.home-shortcuts .el-button {
  height: 42px;
  padding: 0 16px;
  margin-left: 0;
  font-weight: 500;
  color: var(--color-text-secondary);
  background-color: #fff;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  box-shadow: 0 1px 2px rgba(23, 35, 61, 0.04);
  transition: var(--transition-base);
}

.home-shortcuts .el-button:hover {
  color: var(--color-accent);
  background-color: #f7f9ff;
  border-color: rgba(79, 110, 247, 0.4);
  box-shadow: 0 12px 24px -16px rgba(79, 110, 247, 0.45);
  transform: translateY(-2px);
}

.home-shortcuts .el-button .el-icon {
  color: #b6c1d4;
  transition: var(--transition-base);
}

.home-shortcuts .el-button:hover .el-icon {
  color: var(--color-accent);
  transform: translateX(3px);
}

@media (max-width: 640px) {
  .home-hero {
    padding: 24px;
  }

  .home-hero__title {
    font-size: 24px;
  }
}
</style>
