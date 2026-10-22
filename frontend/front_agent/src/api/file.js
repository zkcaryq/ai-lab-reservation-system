// 文件上传接口：目前只有头像图片走这里（后端 files 路由，需 Bearer 鉴权）
import request from '@/utils/request';

// 上传单个文件：入参是原生 File 对象（来自 el-upload 的 http-request 回调 { file }）
export function uploadFileApi(file) {
    // FormData：浏览器原生的"表单数据"容器，multipart 上传的标准载体
    const formData = new FormData();
    // 字段名必须是 file：后端 UploadFile 参数按这个名字从 multipart 里取文件
    formData.append('file', file);
    // 返回值 data.url 是相对路径（/uploads/xxx.png），展示前需 resolveBackendUrl 转绝对
    return request({
        url: "/api/files/upload",
        method: "post",
        data: formData,
        // 声明 multipart 类型；boundary 由浏览器/axios 自动补，不用手写
        headers: {
            'Content-Type': 'multipart/form-data'
        }
    })
}
