<script setup>
// 「Ai助手」整页版：只是 ChatPanel 的一层外壳（玻璃卡 + 标题 + 清空按钮）
// 对话状态与发送逻辑都在 utils/aiChat.js，界面在 components/ChatPanel.vue，
// 所以这一页和右下角悬浮气泡天生共用同一条会话——在页面里问过，打开气泡还在
import { useAiChat } from '@/utils/aiChat'
// 对话面板：消息列表 + 输入框，自带"滚到底部""正在思考"等行为
import ChatPanel from '@/components/ChatPanel.vue'

// clear 是共享动作：气泡那边点「清空会话」和这里点，效果完全一样
const { clear } = useAiChat()
</script>

<template>
  <!-- 玻璃卡：与 manager 子页面族同款外壳；高度按视口算，聊天区自己滚，整页不滚 -->
  <div class="aichat-card">
    <div class="aichat-head">
      <h3 class="aichat-title">AI 智能助手</h3>
      <el-button @click="clear">清空会话</el-button>
    </div>

    <!-- 面板吃掉卡片剩余高度（ChatPanel 内部是 flex 列，消息区 flex:1） -->
    <div class="aichat-body">
      <ChatPanel />
    </div>
  </div>
</template>

<style scoped>
.aichat-card {
  display: flex;
  flex-direction: column;
  /* 顶栏 60px + el-main 上下内边距 32px，余下都给聊天，避免出现整页滚动条 */
  height: calc(100vh - var(--layout-header-height) - 32px);
  min-height: 420px;
  padding: 24px;
  background-color: var(--color-surface-glass);
  backdrop-filter: blur(12px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}

.aichat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.aichat-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
}

/* flex:1 + min-height:0：让面板在卡片里撑满剩余空间且能收缩 */
.aichat-body {
  flex: 1;
  min-height: 0;
}
</style>
