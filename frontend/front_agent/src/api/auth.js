import request from '@/utils/request.js';
export function loginApi(data) {
    return request({
        url: "/api/auth/login",
        method: "post",
        data
    })
}