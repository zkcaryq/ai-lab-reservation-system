<script setup>
// 认证页（登录/注册）共享背景：浅色品牌渐变 + 粒子连线 canvas + 两个模糊光斑
// 抽成组件的原因：两个页面都要同一套背景，canvas 动画逻辑约百行，复制两份必然改漏一处
import { onMounted, onUnmounted, ref } from 'vue'

// canvas 元素引用
const canvasRef = ref(null)
// 粒子数组：每个粒子有位置 (x,y)、速度 (vx,vy)、半径 r
let particles = []
// canvas 2D 绘图上下文
let ctx = null
// requestAnimationFrame 句柄：离开页面时用它取消动画循环
let rafId = 0
// 画布宽高（与窗口尺寸同步）
let width = 0
let height = 0
// 粒子数量与连线距离阈值：两粒子距离小于阈值时画一条渐隐连线
const PARTICLE_COUNT = 70
const LINK_DISTANCE = 130

// 同步 canvas 尺寸与窗口：canvas 的 width/height 属性决定绘图画布大小（不是 CSS 尺寸）
function resizeCanvas() {
  width = canvasRef.value.width = window.innerWidth
  height = canvasRef.value.height = window.innerHeight
  // 读一次布局属性强制同步重排：视口尺寸变化后偶发"布局不刷新"，卡片居中会停留在旧位置
  void document.body.offsetHeight
}

// 生成随机位置 / 随机速度的粒子
function initParticles() {
  particles = Array.from({ length: PARTICLE_COUNT }, () => ({
    x: Math.random() * width,
    y: Math.random() * height,
    vx: (Math.random() - 0.5) * 0.5, // 水平速度：-0.25 ~ 0.25 像素/帧
    vy: (Math.random() - 0.5) * 0.5,
    r: Math.random() * 1.5 + 0.8, // 半径 0.8 ~ 2.3 像素
  }))
}

// 绘制一帧：移动粒子（出界回绕）→ 画连线 → 画粒子
function drawFrame() {
  // 清空上一帧，否则留下拖影
  ctx.clearRect(0, 0, width, height)
  for (const p of particles) {
    p.x += p.vx
    p.y += p.vy
    // 出界回绕：从右边出去就从左边回来，保持画面始终有粒子
    if (p.x < 0) p.x += width
    if (p.x > width) p.x -= width
    if (p.y < 0) p.y += height
    if (p.y > height) p.y -= height
  }
  // 连线：两两配对，透明度随距离增大而衰减（越近越清晰）
  for (let i = 0; i < particles.length; i++) {
    for (let j = i + 1; j < particles.length; j++) {
      const dx = particles[i].x - particles[j].x
      const dy = particles[i].y - particles[j].y
      const dist = Math.hypot(dx, dy)
      if (dist < LINK_DISTANCE) {
        ctx.strokeStyle = `rgba(121, 187, 255, ${(1 - dist / LINK_DISTANCE) * 0.35})`
        ctx.beginPath()
        ctx.moveTo(particles[i].x, particles[i].y)
        ctx.lineTo(particles[j].x, particles[j].y)
        ctx.stroke()
      }
    }
  }
  // 粒子：浅蓝小圆点
  for (const p of particles) {
    ctx.fillStyle = 'rgba(121, 187, 255, 0.8)'
    ctx.beginPath()
    ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
    ctx.fill()
  }
}

// 动画循环：浏览器每帧（约 60fps）回调一次
function loop() {
  drawFrame()
  rafId = requestAnimationFrame(loop)
}

onMounted(() => {
  // 拿到 2D 绘图上下文，之后所有绘制都通过它
  ctx = canvasRef.value.getContext('2d')
  resizeCanvas()
  initParticles()
  // 尊重系统"减少动态效果"设置：只画一帧静态粒子，不跑循环
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (reduceMotion) {
    drawFrame()
  } else {
    loop()
  }
  // 窗口缩放时重算画布尺寸；粒子靠回绕逻辑自然适应新尺寸
  window.addEventListener('resize', resizeCanvas)
})

onUnmounted(() => {
  // 离开页面必须停掉动画循环，否则后台空转吃 CPU（经典泄漏点）
  cancelAnimationFrame(rafId)
  window.removeEventListener('resize', resizeCanvas)
})
</script>

<template>
  <!-- 绝对定位铺满父容器：要求父容器是 position: fixed/relative（登录/注册页均满足） -->
  <div class="auth-bg">
    <!-- 粒子画布：背景层 -->
    <canvas ref="canvasRef" class="particle-canvas"></canvas>
    <!-- 两个模糊光斑：纯 CSS 氛围光，缓慢漂移 -->
    <div class="blob blob-1"></div>
    <div class="blob blob-2"></div>
  </div>
</template>

<style scoped>
/* 背景层：铺满父容器 + 浅色品牌渐变 + 裁掉光斑溢出 */
.auth-bg {
  position: absolute;
  inset: 0;
  overflow: hidden;
  background:
    radial-gradient(900px 620px at 10% 4%, rgba(79, 110, 247, 0.16), transparent 62%),
    radial-gradient(820px 600px at 92% 8%, rgba(139, 92, 246, 0.14), transparent 60%),
    radial-gradient(920px 700px at 50% 112%, rgba(6, 182, 212, 0.12), transparent 64%),
    linear-gradient(160deg, #f9fbff 0%, #eef2ff 52%, #eaf4ff 100%);
}

/* 中央白色柔光：把卡片背后的粒子压淡，保证表单区域干净 */
.auth-bg::after {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: radial-gradient(closest-side at 50% 48%, rgba(255, 255, 255, 0.78), transparent 72%);
}

/* 粒子画布铺满背景层；multiply 把浅蓝连线压成柔和的靛蓝色 */
.particle-canvas {
  position: absolute;
  inset: 0;
  opacity: 0.55;
  mix-blend-mode: multiply;
}

/* 氛围光斑：大半径模糊 + 缓慢漂移动画 */
.blob {
  position: absolute;
  width: 480px;
  height: 480px;
  border-radius: 50%;
  filter: blur(100px);
  opacity: 0.5;
  animation: blob-drift 14s ease-in-out infinite alternate;
}

.blob-1 {
  top: -120px;
  left: -100px;
  background: #c7d2fe;
}

.blob-2 {
  right: -140px;
  bottom: -160px;
  background: #bae6fd;
  animation-delay: -7s;
}

@keyframes blob-drift {
  from {
    transform: translate(0, 0) scale(1);
  }
  to {
    transform: translate(60px, 40px) scale(1.15);
  }
}

/* 系统"减少动态效果"时关闭光斑漂移 */
@media (prefers-reduced-motion: reduce) {
  .blob {
    animation: none;
  }
}
</style>
