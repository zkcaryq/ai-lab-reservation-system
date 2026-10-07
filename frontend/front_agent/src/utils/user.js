import { ref } from 'vue';
import { getUserInfo, setToken, setUserInfo } from '@/utils/auth';
const userInfo = ref(getUserInfo())
export function useUser() {
    function saveLoginData(data){
        setToken(data.token)
        setUserInfo(data.user)
        userInfo.value = data.user
    }
    function updateUser(user){
        setUserInfo(user)
        userInfo.value = user
    }
    function reloadUser(){
        userInfo.value = getUserInfo()
    }
    return {
        userInfo,
        saveLoginData,
        updateUser,
        reloadUser
    }
} // 初始化时从 localStorage 里读取用户信息，没读到就用空对象

