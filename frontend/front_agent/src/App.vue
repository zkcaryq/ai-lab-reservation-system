<template>
  <!-- 根组件：整棵组件树的树根，全局只有一个 -->
  <!-- 唯一职责是渲染一级路由：地址匹配 '/' 时，这里渲染出 Layout.vue 外壳 -->
  <!-- 具体页面（Home 等）由 Layout 内部的第二个 <router-view /> 渲染，形成两级出口链 -->
  <router-view />
</template>
