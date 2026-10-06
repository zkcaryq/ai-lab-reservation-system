// 应用入口：负责"组装插件"并把根组件挂载到页面
// 从 vue 导入 createApp：创建 Vue 应用实例的唯一入口
import { createApp } from 'vue'
// 根组件：整棵组件树的树根，它的模板里只有一个 <router-view />
import App from './App.vue'
// 路由实例：在 src/router/index.js 中定义，包含全部路由匹配规则
import router from './router'
// Element Plus 组件库本体：挂载后全应用才能使用 <el-button />、<el-menu /> 等组件
import ElementPlus from 'element-plus'
// Element Plus 自带组件样式（副作用导入：只执行文件、不绑定变量名）
import 'element-plus/dist/index.css'
// Element Plus 中文语言包：把分页、日期选择器等组件的内置文案换成中文
import zhCn from 'element-plus/es/locale/lang/zh-cn'
// 一次性导入全部图标，得到 { 组件名: 组件定义 } 的对象，如 { Monitor: ..., Lightning: ... }
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
// 项目全局样式：reset + :root 设计变量（@ 是 src 目录的别名，见 vite.config.js）
import '@/assets/css/global.css'

// 用根组件 App.vue 创建应用实例；此刻还没有任何内容渲染到页面上
const app = createApp(App)

// 挂载路由插件：之后组件里才能用 <router-view />，逻辑里才能用 router.push() 跳转
app.use(router)
// 挂载 Element Plus 并传入中文语言包；不传 locale 时组件内置文案默认是英文
app.use(ElementPlus, {
  locale: zhCn,
})
// Object.entries 把图标对象变成 [名字, 组件] 的数组项，循环逐个注册
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  // app.component(名字, 组件) 全局注册：之后任何模板里可直接写 <Monitor />，无需再 import
  app.component(key, component)
}

// 把整棵应用挂载到 index.html 里的 <div id="app"></div> 节点，渲染从这里开始
app.mount('#app')
