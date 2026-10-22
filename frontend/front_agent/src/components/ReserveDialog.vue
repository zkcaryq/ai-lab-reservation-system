<script setup>
// 预约弹窗：Lablist 与 LabEquipment 两页共用的第一个业务组件
// 通信方式 v-model:visible —— 父组件写 :visible + @update:visible；子组件绝不直接改 props（单向数据流）
// 契约（只读核查 2026-10-19）：POST /api/reservation（单数），create 返回 HTTP 201
//   载荷 { lab_id, equipment_id?, date:'YYYY-MM-DD', start_time:'HH:mm', end_time:'HH:mm', remark?≤255 }
//   user_id 不进载荷：后端从 Token 取当前登录用户，前端传了也不认
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { createReservationApi } from '@/api/reservation'

const props = defineProps({
  visible: Boolean, // 弹窗开关：由父组件的 reserveVisible 驱动
  labId: Number,
  labName: String,
  // equipmentId 为空（undefined/null）= 只约实验室；带值 = 约这台设备
  equipmentId: Number,
  equipmentName: String,
})
// 只声明一个事件：关闭时通知父组件改它自己的 visible，子组件不碰 props
const emit = defineEmits(['update:visible'])

const submitting = ref(false) // 提交中：确定按钮 loading，防连点重复提交
const formRef = ref(null) // 弹窗表单引用：提交前单独校验这一份

// 表单初始值：每次打开弹窗都回到这一组（下面用 watch 显式重置）
const FORM_DEFAULTS = { date: '', startTime: '09:00', endTime: '18:00', remark: '' }

const form = reactive({ ...FORM_DEFAULTS })

// 打开时重置：不依赖 el-form 的 resetFields()——它要求每个表单项都有 prop、
// 且重置到"挂载时"的初始值（弹窗内容只挂载一次，第二次打开时它拿到的初始值仍是首次挂载那一刻的），
// 实测上一次填的备注会残留。这里直接按 defaults 灌一遍，行为唯一确定。
watch(
  () => props.visible,
  (val) => {
    if (!val) return
    Object.assign(form, FORM_DEFAULTS)
    // 只清上一次留下的红字校验态，不改值（值已由上一行重置）
    formRef.value?.clearValidate()
  },
)

// 关闭通知：用 computed 做受控开关——读 props.visible，写则 emit 给父组件。
// 为什么不用 @close 事件：那条路径依赖 EP 的过渡动画真正开始；实测在过渡被中断/合成点击下不可靠。
// v-model 绑这个 computed 后，取消/×/遮罩/Esc 四条路径都走同一个 setter。
const innerVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val),
})

// 结束时间交叉校验：value-format 是零填充的 'HH:mm'，字典序 == 时间序，字符串直接比大小即可
// 后端也会拦（「预约的结束时间不能小于开始时间」），前端先拦省一次必败的往返
function validateEndTime(rule, value, callback) {
  if (value && form.startTime && value <= form.startTime) {
    callback(new Error('结束时间需晚于开始时间'))
  } else {
    callback()
  }
}

// rules 的 key 必须与 el-form-item 的 prop 完全一致
// （教程写成 start_time/end_time 而 prop 是 startTime/endTime → 那两条校验静默失效）
const rules = {
  date: [{ required: true, message: '请选择预约日期', trigger: 'change' }],
  startTime: [{ required: true, message: '请选择开始时间', trigger: 'change' }],
  endTime: [
    { required: true, message: '请选择结束时间', trigger: 'change' },
    { validator: validateEndTime, trigger: 'change' },
  ],
}

// 今天之前的日期禁选：后端同样会拒（「预约日期不能小于当前的日期」），禁选比提交后报错友好
function disabledDate(d) {
  return d.getTime() < Date.now() - 86400000 // 减一天的毫秒，把"今天"留在可选范围里
}

// 提交：校验 → 接口 → 2xx 关弹窗；业务失败（时段冲突等）交给拦截器弹后端原文
async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const res = await createReservationApi({
      lab_id: props.labId,
      // 只约实验室时这里是 undefined：JSON.stringify 会丢掉这个键，后端按默认 None 处理
      equipment_id: props.equipmentId,
      date: form.date,
      start_time: form.startTime,
      end_time: form.endTime,
      remark: form.remark,
    })
    // 2xx 区间判定：后端 create 返回 201，写 === 200 会误判失败
    if (res.code >= 200 && res.code < 300) {
      ElMessage.success(res.message || '预约已提交，请等待审核')
      emit('update:visible', false) // 让父组件把 reserveVisible 改回 false
    }
    // 时段冲突/设备维修/实验室关闭：拦截器已弹后端 message，页面不写 else 防双重提示
  } catch {
    // 网络/HTTP 层失败的提示已由 request.js 拦截器统一弹出，这里只终结异常链
  } finally {
    submitting.value = false
  }
}

// 开关的唯一真相在父组件；本组件只通过 emit('update:visible', …) 通知它
</script>

<template>
  <!-- 不套外层 div：el-dialog 自己就是根节点
       append-to-body 必加：EP 的 el-dialog 默认 append-to-body=false，遮罩与弹窗渲染在"当前位置"，
       而它的定位是 position:fixed——祖先只要有 backdrop-filter/transform，fixed 就会以那个祖先为视口，
       于是弹窗跟着卡片滚动、被顶出屏幕（截图里标题跑出可视区、遮罩盖不住左侧菜单就是这个）。
       挂到 body 后脱离卡片的包含块，才真正按浏览器视口居中 -->
  <el-dialog
    v-model="innerVisible"
    :title="equipmentId ? '预约设备' : '预约实验室'"
    width="480px"
    append-to-body
  >
    <!-- 表单：ref 用于提交前校验；值的重置由上面 watch(props.visible) 负责，不靠 resetFields -->
    <el-form ref="formRef" :model="form" :rules="rules" label-width="80px" @submit.prevent>
      <!-- 实验室/设备是"信息"不是"输入"：只读文本行比 disabled 输入框诚实 -->
      <el-form-item label="实验室">
        <span class="reserve-readonly">{{ labName || '-' }}</span>
      </el-form-item>
      <el-form-item label="设备">
        <span class="reserve-readonly">
          {{ equipmentId ? equipmentName || '-' : '—（仅预约实验室）' }}
        </span>
      </el-form-item>
      <el-form-item label="预约日期" prop="date">
        <el-date-picker
          v-model="form.date"
          type="date"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          :disabled-date="disabledDate"
          placeholder="请选择日期"
          class="reserve-full"
        />
      </el-form-item>
      <el-form-item label="开始时间" prop="startTime">
        <el-time-picker
          v-model="form.startTime"
          format="HH:mm"
          value-format="HH:mm"
          placeholder="请选择开始时间"
          class="reserve-full"
        />
      </el-form-item>
      <el-form-item label="结束时间" prop="endTime">
        <el-time-picker
          v-model="form.endTime"
          format="HH:mm"
          value-format="HH:mm"
          placeholder="请选择结束时间"
          class="reserve-full"
        />
      </el-form-item>
      <el-form-item label="备注" prop="remark">
        <!-- prop 必须写：EP 的 resetField() 源码第一行是 `if (!model || !props.prop) return`，
             没有 prop 的项会被 resetFields() 整个跳过 → 上次填的备注会残留到下一次打开（实测到的 bug）
             这里没有校验规则，prop 只为"能被重置"服务 -->
        <el-input
          v-model="form.remark"
          type="textarea"
          :rows="3"
          maxlength="255"
          show-word-limit
          placeholder="选填，例如：做课程实验"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="innerVisible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
/* 三个选择器控件撑满表单内容列（替代教程的逐行内联 style） */
.reserve-full {
  width: 100%;
}

/* 只读信息行：与输入框同字号、同高度，但没有边框，一眼看出"不可编辑" */
.reserve-readonly {
  font-size: 14px;
  line-height: 32px;
  color: var(--color-text-primary);
}
</style>
