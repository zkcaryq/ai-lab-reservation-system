// ref：用来创建下面这个模块级响应式 userInfo
import { ref } from 'vue';
// 本地存储的唯一读写出口在 utils/auth.js：这里只复用它的函数，不直接碰 localStorage
import { getUserInfo, setToken, setUserInfo } from '@/utils/auth';
// 模块级 ref = 手写的全局共享 store：所有组件里调用 useUser() 拿到的都是同一个 userInfo
// 初始值在模块加载时（页面刷新）从 localStorage 读一次；没读到则 getUserInfo 返回 null
const userInfo = ref(getUserInfo())
// 组合式函数：组件在 setup 里写 const { userInfo, saveLoginData } = useUser() 获取登录态能力
export function useUser() {
    // 保存登录结果：登录成功后调用；data = 后端返回的 { token, user }
    function saveLoginData(data){
        setToken(data.token) // token 写入 localStorage：之后每个请求由请求拦截器自动带上
        setUserInfo(data.user) // 用户信息序列化后写入 localStorage：刷新页面仍能读回
        userInfo.value = data.user // 同步更新响应式 ref：顶栏等引用 userInfo 的组件立即重新渲染
    }
    // 更新用户信息：修改个人资料等场景调用；只换 user，不动 token
    function updateUser(user){
        setUserInfo(user)
        userInfo.value = user
    }
    // 从本地重新读回：localStorage 被外部改动（如别的标签页清除）后手动同步一次
    function reloadUser(){
        userInfo.value = getUserInfo()
    }
    // 统一暴露：userInfo 是模块级共享的同一个 ref；三个方法每次调用虽新建，但操作的都是它
    return {
        userInfo,
        saveLoginData,
        updateUser,
        reloadUser
    }
}
