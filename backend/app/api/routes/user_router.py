"""当前用户资料、密码以及管理员用户列表接口。"""

from fastapi import APIRouter, Path, Query, status

from app.api.dependencies import CurrentAdmin, CurrentUser, DbSession
from app.schemas.apiresponse import ApiResponse
from app.schemas.user_schemas import (
    AdminCreateUserRequest,
    AdminUpdateUserRequest,
    PasswordUpdateRequest,
    UserPageResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.services.auth import user_services

# 本Router已经在app/api/router.py中挂到/api前缀下，所以最终路径以/api/user开头。
router = APIRouter(prefix="/user", tags=["用户信息接口"])


@router.get("/me")
async def get_user_info(current_user: CurrentUser) -> ApiResponse:
    """返回Bearer Token对应的当前用户信息。

    Router开始执行时，CurrentUser已经完成Token验证、数据库查询和状态检查，
    因此这里拿到的一定是仍然存在且状态正常的User对象。
    """

    # UserResponse只选择允许公开的用户字段，不会把password哈希返回客户端。
    user_data = UserResponse.model_validate(current_user)

    # 由ApiResponse.success()统一生成code/message/data外层结构。
    return ApiResponse.success(data=user_data)


@router.patch("/me")
async def update_user_info(
    session: DbSession,
    current_user: CurrentUser,
    data: UserUpdateRequest,
) -> ApiResponse:
    """修改Bearer Token对应用户本次提交的个人资料字段。"""

    # 这里必须调用导入的Service函数，不能调用当前Router函数本身。
    # 导入时使用_service后缀，避免两个update_user_info同名造成无限递归。
    updated_user = await user_services.update_user_info(
        session,
        # Service参数列表中的*要求这两个参数必须使用名称传入。
        user=current_user,
        data=data,
    )

    # Service返回User ORM对象；Router转换成不会包含password的响应Schema。
    user_data = UserResponse.model_validate(updated_user)

    # 使用项目统一成功响应结构返回更新后的完整用户资料。
    return ApiResponse.success(
        message="个人信息修改成功！Ovo!",
        data=user_data,
    )


@router.patch("/password")
async def update_user_password(
    session: DbSession,
    current_user: CurrentUser,
    data: PasswordUpdateRequest,
) -> ApiResponse:
    """验证旧密码后，为当前登录用户保存新密码哈希。"""

    # 旧密码校验、新旧密码比较、哈希和事务都由Service完成。
    await user_services.update_password(
        session,
        user=current_user,
        data=data,
    )

    # 修改成功使用HTTP 200；ApiResponse.success()中的JSON code也默认为200。
    return ApiResponse.success(message="密码修改成功！Ovo!")


@router.get("/list")
async def get_user_list(
    session: DbSession,
    _current_admin: CurrentAdmin,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    keywords: str | None = Query(default=None, max_length=50),
) -> ApiResponse:
    """只允许管理员分页查询用户，并按账号或名称模糊搜索。

    FastAPI进入函数前会依次解析Query参数、创建AsyncSession并执行CurrentAdmin。
    任一依赖失败都会直接返回401、403或422，本函数不会开始执行。
    """

    # _current_admin虽然没有在函数体读取，但其类型会触发完整管理员鉴权链。
    # 下划线前缀明确表示“只需要依赖产生的校验副作用，不读取注入值”。

    # 把请求级Session和经过Query校验的分页参数交给异步Service。
    # page至少为1，page_size范围1～100，keywords最长50字符。
    users, total = await user_services.get_user_page_list(
        session,
        page=page,
        page_size=page_size,
        keywords=keywords,
    )

    # 列表推导式会逐个把User ORM对象转换成UserResponse。
    # UserResponse只声明公开字段，不包含password，因此哈希不会泄露给前端。
    page_data = UserPageResponse(
        list=[UserResponse.model_validate(user) for user in users],
        total=total,
    )

    # 即使搜索结果为空也应返回HTTP 200、list=[]、total=0，而不是404。
    # ApiResponse.success()负责生成统一的code/message/data外层结构。
    return ApiResponse.success(data=page_data)


# 空路径会和Router自身的/user前缀组合成POST /api/user。
# status_code设置真实HTTP状态码；响应JSON里的code还要在success()中同步设置为201。
@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    data: AdminCreateUserRequest,
    session: DbSession,
    _current_admin: CurrentAdmin,
) -> ApiResponse:
    """只允许管理员创建用户，成功返回201 Created。"""

    # _current_admin虽然未在函数体读取，但会触发JWT、账号状态和管理员角色检查。
    # Router把校验完成的请求Schema和请求级Session交给Service。
    user = await user_services.create_user(
        session,
        data=data,
    )

    # UserResponse只读取公开字段，不会把新用户的Argon2id密码哈希返回前端。
    user_data = UserResponse.model_validate(user)

    # 装饰器与JSON code同时使用201，避免出现“真实HTTP 201、JSON code 200”。
    return ApiResponse.success(
        code=status.HTTP_201_CREATED,
        message="用户创建成功！Ovo!",
        data=user_data,
    )


# 动态/{user_id}必须写在/me、/password和/list等固定路径之后，避免路径抢占。
@router.patch("/{user_id}")
async def update_user(
    data: AdminUpdateUserRequest,
    session: DbSession,
    _current_admin: CurrentAdmin,
    user_id: int = Path(gt=0),
) -> ApiResponse:
    """只允许管理员部分修改指定用户。"""

    # FastAPI的Path(gt=0)会在进入函数前验证ID必须大于0，失败自动返回HTTP 422。
    user = await user_services.update_user(
        session,
        user_id=user_id,
        data=data,
    )

    # 把更新后的User ORM转换成公开响应字段。
    user_data = UserResponse.model_validate(user)

    return ApiResponse.success(
        message="用户信息修改成功！Ovo!",
        data=user_data,
    )


@router.delete("/{user_id}")
async def delete_user(
    session: DbSession,
    current_admin: CurrentAdmin,
    user_id: int = Path(gt=0),
) -> ApiResponse:
    """只允许管理员删除指定用户，但禁止删除当前登录账号。"""

    # 自删除、目标不存在及外键冲突都由Service转换成业务异常。
    await user_services.delete_user(
        session,
        user_id=user_id,
        current_admin_id=current_admin.id,
    )

    # 因为需要返回成功提示，所以使用HTTP 200；204响应不能携带JSON body。
    return ApiResponse.success(message="用户删除成功！Ovo!")
