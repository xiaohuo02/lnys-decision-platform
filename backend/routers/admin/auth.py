# -*- coding: utf-8 -*-
"""backend/routers/admin/auth.py

管理后台认证接口
POST /admin/auth/login   → 获取 JWT token
GET  /admin/auth/me      → 查询当前用户信息
"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.rate_limiter import login_limiter
from backend.core.exceptions import AppError
from backend.database import get_async_db
from backend.middleware.auth import create_access_token, get_current_user, CurrentUser
from backend.models.auth import User, UserRole, Role

router = APIRouter(tags=["admin-auth"])


class LoginBody(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    username:     str
    roles:        list


@router.post("/auth/login", response_model=TokenResponse)
async def admin_login(
    body: LoginBody,
    request: Request,
    _rate_limit: None = Depends(login_limiter),
    db: AsyncSession = Depends(get_async_db),
):
    """
    验证用户名/密码，返回 JWT token。
    密码使用 bcrypt 哈希比较。
    开发环境：如找不到用户，允许使用 settings.SECRET_KEY 作为万能密钥。
    """
    from passlib.context import CryptContext
    from backend.config import settings

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

    # 查询用户（MySQL 不可达时自动降级到开发后门快捷登录）
    try:
        result = await db.execute(select(User).where(User.username == body.username))
        user = result.scalars().first()
    except Exception as db_err:
        if settings.DEV_BACKDOOR_ENABLED and body.username == "admin" and body.password == "admin":
            token = create_access_token("admin", ["platform_admin"])
            return TokenResponse(access_token=token, username="admin", roles=["platform_admin"])
        raise AppError(503, f"数据库不可达: {db_err}")

    if user is None:
        if settings.DEV_BACKDOOR_ENABLED and body.username == "admin" and body.password == "admin":
            token = create_access_token("admin", ["platform_admin"])
            return TokenResponse(access_token=token, username="admin", roles=["platform_admin"])
        raise AppError(401, "用户名或密码错误")

    if not user.is_active:
        raise AppError(403, "账号已禁用")

    if not pwd_ctx.verify(body.password, user.hashed_pw):
        raise AppError(401, "用户名或密码错误")

    # 获取用户角色（单次 JOIN 查询）
    role_result = await db.execute(
        select(Role.role_name)
        .join(UserRole, UserRole.role_id == Role.role_id)
        .where(UserRole.user_id == user.user_id)
    )
    roles = [r[0] for r in role_result.fetchall()]

    token = create_access_token(body.username, roles)
    return TokenResponse(access_token=token, username=body.username, roles=roles)


class RegisterBody(BaseModel):
    real_name: str
    password: str
    auth_code: str


class RegisterResponse(BaseModel):
    username: str
    display_name: str
    message: str


@router.post("/auth/register", response_model=RegisterResponse)
async def admin_register(body: RegisterBody, db: AsyncSession = Depends(get_async_db)):
    """
    员工自助注册接口。
    1. 校验企业授权码
    2. 真实姓名 → 拼音小写作为 username
    3. 密码 bcrypt 加密
    4. 默认分配 employee 角色（只读）
    5. 若 username 已存在则追加数字后缀
    """
    from passlib.context import CryptContext
    from backend.config import settings
    import uuid

    # 1. 校验授权码
    if body.auth_code != settings.REGISTER_AUTH_CODE:
        raise AppError(403, "授权码无效，请联系管理员获取")

    if not body.real_name.strip():
        raise AppError(400, "真实姓名不能为空")

    if len(body.password) < 6:
        raise AppError(400, "密码长度不能少于 6 位")

    # 2. 姓名 → 拼音账号
    username = _to_pinyin(body.real_name.strip())
    if not username:
        raise AppError(400, "无法从姓名生成账号，请使用常见汉字")

    # 3. 唯一性：若已存在则追加数字
    base_username = username
    counter = 1
    while True:
        dup = await db.execute(select(User).where(User.username == username))
        if dup.scalars().first() is None:
            break
        username = f"{base_username}{counter}"
        counter += 1

    # 4. 创建用户
    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    user_id = str(uuid.uuid4())
    new_user = User(
        user_id=user_id,
        username=username,
        display_name=body.real_name.strip(),
        hashed_pw=pwd_ctx.hash(body.password),
        is_active=True,
    )
    db.add(new_user)

    # 5. 分配 employee 角色
    role_result = await db.execute(select(Role).where(Role.role_name == "employee"))
    employee_role = role_result.scalars().first()
    if employee_role is None:
        # 自动创建 employee 角色（首次注册时）
        employee_role = Role(
            role_id=str(uuid.uuid4()),
            role_name="employee",
            description="默认员工角色（只读业务空间，等待管理员授权）",
        )
        db.add(employee_role)
        await db.flush()

    db.add(UserRole(
        user_id=user_id,
        role_id=employee_role.role_id,
        granted_by="system_register",
    ))

    await db.commit()
    return RegisterResponse(
        username=username,
        display_name=body.real_name.strip(),
        message="注册成功，请等待管理员授予操作权限",
    )


# ── 姓名→拼音转换 ──────────────────────────────────────────────────
_PINYIN_MAP = {
    '赵':'zhao','钱':'qian','孙':'sun','李':'li','周':'zhou','吴':'wu','郑':'zheng','王':'wang',
    '冯':'feng','陈':'chen','褚':'chu','卫':'wei','蒋':'jiang','沈':'shen','韩':'han','杨':'yang',
    '朱':'zhu','秦':'qin','尤':'you','许':'xu','何':'he','吕':'lv','施':'shi','张':'zhang',
    '孔':'kong','曹':'cao','严':'yan','华':'hua','金':'jin','魏':'wei','陶':'tao','姜':'jiang',
    '戚':'qi','谢':'xie','邹':'zou','喻':'yu','柏':'bai','水':'shui','窦':'dou','章':'zhang',
    '云':'yun','苏':'su','潘':'pan','葛':'ge','奚':'xi','范':'fan','彭':'peng','郎':'lang',
    '鲁':'lu','韦':'wei','昌':'chang','马':'ma','苗':'miao','凤':'feng','花':'hua','方':'fang',
    '俞':'yu','任':'ren','袁':'yuan','柳':'liu','邓':'deng','鲍':'bao','史':'shi','唐':'tang',
    '费':'fei','廉':'lian','岑':'cen','薛':'xue','雷':'lei','贺':'he','倪':'ni','汤':'tang',
    '滕':'teng','殷':'yin','罗':'luo','毕':'bi','郝':'hao','邬':'wu','安':'an','常':'chang',
    '乐':'le','于':'yu','时':'shi','傅':'fu','皮':'pi','卞':'bian','齐':'qi','康':'kang',
    '伍':'wu','余':'yu','元':'yuan','卜':'bu','顾':'gu','孟':'meng','平':'ping','黄':'huang',
    '穆':'mu','萧':'xiao','尹':'yin','姚':'yao','邵':'shao','湛':'zhan','汪':'wang','祁':'qi',
    '禹':'yu','狄':'di','米':'mi','贝':'bei','明':'ming','臧':'zang','计':'ji','伏':'fu',
    '成':'cheng','戴':'dai','谈':'tan','宋':'song','茅':'mao','庞':'pang','熊':'xiong','纪':'ji',
    '舒':'shu','屈':'qu','项':'xiang','祝':'zhu','董':'dong','梁':'liang','杜':'du','阮':'ruan',
    '蓝':'lan','闵':'min','席':'xi','季':'ji','麻':'ma','强':'qiang','贾':'jia','路':'lu',
    '娄':'lou','危':'wei','江':'jiang','童':'tong','颜':'yan','郭':'guo','梅':'mei','盛':'sheng',
    '林':'lin','刁':'diao','钟':'zhong','徐':'xu','丘':'qiu','骆':'luo','高':'gao','夏':'xia',
    '蔡':'cai','田':'tian','樊':'fan','胡':'hu','凌':'ling','霍':'huo','虞':'yu','万':'wan',
    '支':'zhi','柯':'ke','管':'guan','卢':'lu','莫':'mo','白':'bai','房':'fang','裘':'qiu',
    '缪':'miao','干':'gan','解':'xie','应':'ying','宗':'zong','丁':'ding','宣':'xuan','贲':'ben',
    '邱':'qiu','包':'bao','诸':'zhu','左':'zuo','石':'shi','崔':'cui','吉':'ji','钮':'niu',
    '龚':'gong','程':'cheng','嵇':'ji','邢':'xing','滑':'hua','裴':'pei','陆':'lu','荣':'rong',
    '翁':'weng','荀':'xun','羊':'yang','甄':'zhen','曲':'qu','家':'jia','封':'feng','芮':'rui',
    '储':'chu','靳':'jin','汲':'ji','邴':'bing','糜':'mi','松':'song','段':'duan','富':'fu',
    '巫':'wu','乌':'wu','焦':'jiao','巴':'ba','弓':'gong','牧':'mu','隗':'wei','山':'shan',
    '谷':'gu','车':'che','侯':'hou','宓':'mi','蓬':'peng','全':'quan','郗':'xi','班':'ban',
    '仰':'yang','秋':'qiu','仲':'zhong','伊':'yi','宫':'gong','宁':'ning','仇':'qiu','栾':'luan',
    '暴':'bao','甘':'gan','钭':'tou','厉':'li','戎':'rong','祖':'zu','武':'wu','符':'fu',
    '刘':'liu','景':'jing','詹':'zhan','束':'shu','龙':'long','叶':'ye','幸':'xing','司':'si',
    '黎':'li','溥':'pu','印':'yin','宿':'su','丛':'cong','连':'lian','单':'shan','洪':'hong',
    # 常用名用字
    '伟':'wei','芳':'fang','娜':'na','敏':'min','静':'jing','丽':'li','强':'qiang','磊':'lei',
    '军':'jun','洋':'yang','勇':'yong','艳':'yan','杰':'jie','涛':'tao','春':'chun','飞':'fei',
    '超':'chao','浩':'hao','亮':'liang','平':'ping','辉':'hui','刚':'gang','桂':'gui','英':'ying',
    '红':'hong','文':'wen','建':'jian','国':'guo','志':'zhi','天':'tian','新':'xin','海':'hai',
    '波':'bo','宇':'yu','鑫':'xin','博':'bo','睿':'rui','晨':'chen','旭':'xu','俊':'jun',
    '子':'zi','佳':'jia','思':'si','雨':'yu','欣':'xin','怡':'yi','琳':'lin','瑶':'yao',
    '洁':'jie','颖':'ying','婷':'ting','雪':'xue','慧':'hui','梦':'meng','涵':'han','紫':'zi',
    '妍':'yan','月':'yue','星':'xing','阳':'yang','德':'de','正':'zheng','庆':'qing','瑞':'rui',
    '峰':'feng','昊':'hao','翔':'xiang','鹏':'peng','小':'xiao','大':'da','中':'zhong',
    '长':'chang','兴':'xing','家':'jia','永':'yong','美':'mei','玉':'yu','凤':'feng',
    '兰':'lan','燕':'yan','秀':'xiu','珍':'zhen','玲':'ling','冰':'bing','雅':'ya',
    '萍':'ping','莉':'li','彬':'bin','松':'song','柏':'bai','岩':'yan','明':'ming',
    '光':'guang','立':'li','东':'dong','南':'nan','西':'xi','北':'bei','清':'qing',
    '毅':'yi','恒':'heng','忠':'zhong','义':'yi','信':'xin','仁':'ren','礼':'li',
    '智':'zhi','勤':'qin','俭':'jian','和':'he','谦':'qian','祥':'xiang','福':'fu',
    '禄':'lu','寿':'shou','康':'kang','宁':'ning','乐':'le','成':'cheng','功':'gong',
    '达':'da','发':'fa','财':'cai','富':'fu','贵':'gui','荣':'rong','华':'hua',
}


def _to_pinyin(name: str) -> str:
    """将中文姓名转为拼音小写字母（仅用于生成 username）"""
    result = []
    for ch in name:
        if ch in _PINYIN_MAP:
            result.append(_PINYIN_MAP[ch])
        elif ch.isascii() and ch.isalpha():
            result.append(ch.lower())
        # 跳过空格和其他字符
    return "".join(result)


@router.get("/auth/me")
async def admin_me(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    """返回当前用户信息，包含 display_name"""
    data = {"username": user.username, "roles": user.roles, "display_name": ""}
    try:
        result = await db.execute(select(User).where(User.username == user.username))
        db_user = result.scalars().first()
        if db_user:
            data["display_name"] = db_user.display_name or ""
    except Exception:
        pass
    return data
