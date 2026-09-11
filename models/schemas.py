from __future__ import annotations

import datetime
import re
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from models.domain import ApplicationStatus, Gender, OrderStatus


def _validate_password_complexity(v: str) -> str:
    """新设密码必须同时包含字母和数字；登录不校验复杂度，避免锁死历史弱密码用户。"""
    if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
        raise ValueError("密码需至少 6 位，且同时包含字母和数字")
    return v


# ── 教员 ──

class TeacherRegisterRequest(BaseModel):
    """C 端：教员注册"""
    name: str = Field(..., min_length=1, max_length=20)
    gender: Gender
    phone: str = Field(..., min_length=11, max_length=15)
    wechat_id: str = Field(..., min_length=1, max_length=50)
    school: str = Field(..., min_length=1, max_length=50)
    is_985_211: bool = False
    is_985: bool = False
    is_211: bool = False
    is_double_first_class: bool = False
    major: str | None = Field(None, max_length=50)
    grade: str | None = Field(None, max_length=20)
    highlights: str | None = None
    lng: Decimal | None = None
    lat: Decimal | None = None


class TeacherSummary(BaseModel):
    id: int
    name: str
    gender: Gender
    school: str
    is_985_211: bool
    is_985: bool = False
    is_211: bool = False
    is_double_first_class: bool = False
    major: str | None
    grade: str | None
    highlights: str | None
    # 联系方式仅下发给出过该接口的调用方（教员只看自己，B 端用于线下沟通收定金）
    phone: str | None = None
    wechat_id: str | None = None
    # 信用画像：由投递列表接口按批量聚合填充
    completed_count: int = 0
    violation_count: int = 0
    avg_rating: float | None = None

    model_config = {"from_attributes": True}


class TeacherResponse(BaseModel):
    id: int
    name: str
    gender: Gender
    school: str
    is_985_211: bool
    is_985: bool = False
    is_211: bool = False
    is_double_first_class: bool = False
    major: str | None
    grade: str | None
    highlights: str | None
    # 教员自己的资料（仅本人 token 可见），编辑资料时用于回填
    phone: str | None = None
    wechat_id: str | None = None
    lng: float | None = None
    lat: float | None = None
    home_area: str | None = None

    model_config = {"from_attributes": True}


class TeacherProfileUpdate(BaseModel):
    """教员自助编辑基础资料与常驻地；未传字段不修改。"""
    name: str | None = Field(None, min_length=1, max_length=20)
    gender: Gender | None = None
    wechat_id: str | None = Field(None, min_length=1, max_length=50)
    school: str | None = Field(None, min_length=1, max_length=50)
    major: str | None = Field(None, max_length=50)
    grade: str | None = Field(None, max_length=20)
    highlights: str | None = None
    home_area: str | None = Field(None, max_length=100)
    lng: float | None = Field(None, ge=-180, le=180)
    lat: float | None = Field(None, ge=-90, le=90)


class TeacherResumeBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=50)
    teaching_subjects: str = Field(..., min_length=1, max_length=120)
    teaching_grades: str = Field(..., min_length=1, max_length=120)
    experience: str = Field(..., min_length=1)
    strengths: str | None = None
    availability: str | None = Field(None, max_length=120)
    expected_rate: str | None = Field(None, max_length=50)
    is_default: bool = False


class TeacherResumeCreate(TeacherResumeBase):
    pass


class TeacherResumeUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=50)
    teaching_subjects: str | None = Field(None, min_length=1, max_length=120)
    teaching_grades: str | None = Field(None, min_length=1, max_length=120)
    experience: str | None = Field(None, min_length=1)
    strengths: str | None = None
    availability: str | None = Field(None, max_length=120)
    expected_rate: str | None = Field(None, max_length=50)
    is_default: bool | None = None


class TeacherResumeResponse(TeacherResumeBase):
    id: int
    teacher_id: int
    created_at: datetime.datetime
    updated_at: datetime.datetime | None = None

    model_config = {"from_attributes": True}


# ── 认证 ──

class WxLoginRequest(BaseModel):
    code: str = Field(..., description="wx.login() 返回的 code")


class PhoneInviteLoginRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=15)
    invite_code: str = Field(..., min_length=1, max_length=20)
    password: str = Field(..., min_length=6, max_length=64)

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, v: str) -> str:
        normalized = v.strip().replace(" ", "")
        if not normalized.isdigit() or len(normalized) != 11:
            raise ValueError("请输入 11 位手机号")
        return normalized

    @field_validator("invite_code")
    @classmethod
    def valid_invite_code(cls, v: str) -> str:
        return v.strip()


class PhoneInviteRegisterRequest(PhoneInviteLoginRequest):
    name: str = Field(..., min_length=1, max_length=20)
    gender: Gender
    wechat_id: str = Field(..., min_length=1, max_length=50)
    school: str = Field(..., min_length=1, max_length=50)
    is_985_211: bool = False
    is_985: bool = False
    is_211: bool = False
    is_double_first_class: bool = False
    major: str | None = Field(None, max_length=50)
    grade: str | None = Field(None, max_length=20)
    highlights: str | None = None

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        return _validate_password_complexity(v)


class OwnerLoginRequest(BaseModel):
    access_code: str = Field(..., min_length=1, max_length=50)


class TenantLoginRequest(BaseModel):
    invite_code: str = Field(..., min_length=1, max_length=20)
    password: str = Field(..., min_length=6, max_length=64)

    @field_validator("invite_code")
    @classmethod
    def valid_invite_code(cls, v: str) -> str:
        return v.strip()


class PasswordChangeRequest(BaseModel):
    old_password: str = Field(..., min_length=6, max_length=64)
    new_password: str = Field(..., min_length=6, max_length=64)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        return _validate_password_complexity(v)


class TenantBrief(BaseModel):
    id: int
    tenant_name: str
    invite_code: str
    # 教员端展示中介微信，便于线下沟通退定金/试课安排
    contact_wechat: str | None = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    token: str
    role: str
    teacher: TeacherResponse | None = None
    tenant: TenantBrief | None = None


class TenantCreateRequest(BaseModel):
    tenant_name: str = Field(..., min_length=1, max_length=50)
    contact_wechat: str = Field(..., min_length=1, max_length=50)
    invite_code: str | None = Field(None, min_length=4, max_length=20)
    # 不填时由服务端生成随机密码，明文仅在创建响应中返回一次
    password: str | None = Field(None, min_length=6, max_length=64)

    @field_validator("invite_code")
    @classmethod
    def normalize_invite_code(cls, v: str | None) -> str | None:
        return v.strip() if v else v

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str | None) -> str | None:
        return _validate_password_complexity(v) if v else v


class TenantStatusUpdate(BaseModel):
    is_active: bool


class TenantAdminResponse(BaseModel):
    id: int
    tenant_name: str
    invite_code: str
    contact_wechat: str
    is_active: bool
    created_at: datetime.datetime
    # 仅创建/重置密码时返回一次明文，其余场景为 None
    initial_password: str | None = None

    model_config = {"from_attributes": True}


class DemoTeacherResponse(BaseModel):
    id: int
    name: str
    phone: str
    school: str
    major: str | None
    grade: str | None
    highlights: str | None
    lng: float | None = None
    lat: float | None = None
    teaching_subjects: str | None = None
    teaching_grades: str | None = None


class TeacherAdminItem(BaseModel):
    """老板端教员管理列表项。"""

    id: int
    name: str
    gender: Gender
    phone: str
    school: str
    major: str | None
    grade: str | None
    is_banned: bool
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class TeacherBanRequest(BaseModel):
    is_banned: bool


class DemoCountsResponse(BaseModel):
    tenants: int
    teachers: int
    resumes: int


class DemoDataResponse(BaseModel):
    counts: DemoCountsResponse
    tenants: list[TenantAdminResponse]
    teachers: list[DemoTeacherResponse]


# ── 订单解析 ──

class BatchParseRequest(BaseModel):
    raw_text: str = Field(
        ...,
        min_length=1,
        max_length=20000,
        description="微信聊天复制文本；上限 2 万字符，防止单请求放大 AI 调用费用",
    )


class ParsedOrderItem(BaseModel):
    raw_id: str
    raw_text: str
    grade_subject: str
    requirements: str | None = ""
    price_total: str = "待定"
    base_price: float = 0.0
    weekly_frequency: int = 1
    is_summer_vacation: bool = False
    address: str
    subway_remark: str | None = None
    lesson_count: int | None = None
    lesson_hours: float = 2.0

    # 服务端填充
    lng: float | None = None
    lat: float | None = None
    fuzzy_address: str | None = None
    calculated_info_fee: float | None = None
    deposit_amount: float | None = None
    balance_amount: float | None = None
    needs_manual_price: bool = False
    parser_source: str = "通用解析"
    parser_confidence: str = "medium"
    missing_fields: list[str] = Field(default_factory=list)
    needs_manual_review: bool = False


class BatchParseResponse(BaseModel):
    items: list[ParsedOrderItem]
    count: int
    # 部分段解析失败时的原因列表：成功段照常返回，失败原因随响应提示
    warnings: list[str] = Field(default_factory=list)


# ── 订单导入 ──

class OrderImportItem(BaseModel):
    raw_id: str
    raw_text: str
    grade_subject: str
    requirements: str | None = ""
    price_total: str
    base_price: float = Field(..., ge=0, le=999999.99)
    weekly_frequency: int = Field(default=1, ge=1, le=14)
    is_summer_vacation: bool = False
    exact_address: str | None = None
    parent_phone: str | None = None
    subway_remark: str | None = None
    fuzzy_address: str
    # 经纬度范围约束：越界坐标会让 Redis GEOADD 失败，订单入库后却永远不上地图
    lng: float = Field(..., ge=-180, le=180)
    lat: float = Field(..., ge=-85, le=85)
    calculated_info_fee: float = Field(..., ge=0, le=999999.99)
    deposit_amount: float = Field(..., ge=0, le=999999.99)
    balance_amount: float = Field(..., ge=0, le=999999.99)

    @field_validator("base_price", "calculated_info_fee", "deposit_amount", "balance_amount")
    @classmethod
    def non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("金额不能为负数")
        return v


class BatchImportRequest(BaseModel):
    items: list[OrderImportItem] = Field(..., min_length=1, max_length=200)


class BatchImportResponse(BaseModel):
    imported: int
    skipped_duplicates: list[str] = []


class OrderUpdateRequest(BaseModel):
    grade_subject: str | None = Field(None, min_length=1, max_length=50)
    requirements: str | None = None
    price_total: str | None = Field(None, min_length=1, max_length=50)
    base_price: float | None = Field(None, ge=0, le=999999.99)
    weekly_frequency: int | None = Field(None, ge=1, le=14)
    is_summer_vacation: bool | None = None
    exact_address: str | None = Field(None, max_length=255)
    parent_phone: str | None = Field(None, max_length=20)
    fuzzy_address: str | None = Field(None, min_length=1, max_length=100)
    subway_remark: str | None = Field(None, max_length=100)
    lng: float | None = Field(None, ge=-180, le=180)
    lat: float | None = Field(None, ge=-85, le=85)
    expired_at: datetime.datetime | None = None

    @field_validator("base_price")
    @classmethod
    def valid_base_price(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("课酬不能为负数")
        return v


# ── 订单响应 ──

class OrderBrief(BaseModel):
    """地图 Marker 用的轻量数据"""
    id: int
    grade_subject: str
    price_total: str
    base_price: float
    weekly_frequency: int
    fuzzy_address: str
    subway_remark: str | None
    lng: float
    lat: float
    calculated_info_fee: float
    deposit_amount: float
    balance_amount: float
    needs_manual_price: bool = False
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class OrderDetailResponse(OrderBrief):
    raw_id: str
    raw_text: str
    requirements: str | None = None
    exact_address: str | None = None
    parent_phone: str | None = None
    is_summer_vacation: bool = False
    status: OrderStatus
    expired_at: datetime.datetime


class AgentBoardResponse(BaseModel):
    tenant_name: str
    invite_code: str
    # 教员联系中介的微信（退定金、改约试课等线下沟通入口）
    contact_wechat: str | None = None
    orders: list[OrderBrief]


class RecommendationScoreBreakdown(BaseModel):
    distance: int
    subject: int
    grade: int
    school: int
    price: int
    history: int


class RecommendedResumeSnapshot(TeacherResumeBase):
    id: int
    teacher_id: int

    model_config = {"from_attributes": True}


class TeacherOrderRecommendationItem(OrderBrief):
    status: OrderStatus
    total_score: int
    score_breakdown: RecommendationScoreBreakdown
    reasons: list[str]
    distance_km: float | None = None
    already_applied: bool = False
    application_id: int | None = None
    application_status: ApplicationStatus | None = None
    matched_subject: str | None = None
    matched_grade: str | None = None
    best_resume: RecommendedResumeSnapshot | None = None


class TeacherOrderRecommendationResponse(BaseModel):
    tenant_name: str
    invite_code: str
    count: int
    items: list[TeacherOrderRecommendationItem]


# ── 状态流转 ──

class TransitRequest(BaseModel):
    target_status: OrderStatus


class TransitResponse(BaseModel):
    order_id: int
    previous_status: OrderStatus
    current_status: OrderStatus


class BatchStatusUpdateRequest(BaseModel):
    order_ids: list[int] = Field(..., min_length=1, max_length=200)
    target_status: OrderStatus


class BatchStatusUpdateResponse(BaseModel):
    updated: int
    skipped: int = 0


# ── 地址解锁响应 ──

class AddressUnlockResponse(BaseModel):
    exact_address: str | None
    parent_phone: str | None


# ── 投递 ──

class ApplicationResponse(BaseModel):
    id: int
    order_id: int
    raw_order_id: str | None = None
    teacher_id: int
    tenant_id: int
    tenant_name: str | None = None
    order_grade_subject: str | None = None
    order_price_total: str | None = None
    order_fuzzy_address: str | None = None
    resume_id: int | None = None
    resume: TeacherResumeResponse | None = None
    teacher: TeacherSummary | None = None
    status: ApplicationStatus
    proposed_price: float | None = None
    applied_at: datetime.datetime
    shortlisted_at: datetime.datetime | None = None
    deposit_paid_at: datetime.datetime | None = None
    balance_paid_at: datetime.datetime | None = None
    rejected_at: datetime.datetime | None = None
    refunded_at: datetime.datetime | None = None

    model_config = {"from_attributes": True}


# ── 财务 ──

class FinancialRecordResponse(BaseModel):
    id: int
    order_id: int
    tenant_id: int
    teacher_id: int
    amount: float
    type: str
    remark: str | None
    operator_role: str | None = None
    created_at: datetime.datetime
    # 对账可读性：直接给出科目/原始单号/教员姓名，避免只有内部 ID 无法辨认
    order_subject: str | None = None
    order_raw_id: str | None = None
    teacher_name: str | None = None
    teacher_school: str | None = None
    raw_order_id: str | None = None  # 教员端结算单兼容字段

    model_config = {"from_attributes": True}


class FinancialSummaryResponse(BaseModel):
    deposit_in: float = 0
    balance_in: float = 0
    refund_out: float = 0
    forfeit: float = 0
    net_amount: float = 0
    records: list[FinancialRecordResponse]


class TenantRoiSummary(BaseModel):
    """中介工作台「本月为你」：当月经营数据聚合（UTC 自然月口径）。"""
    month: str
    orders_imported: int = 0
    applications_received: int = 0
    deals_completed: int = 0
    deposit_in: float = 0
    balance_in: float = 0
    refund_out: float = 0
    forfeit: float = 0
    net_amount: float = 0
    teacher_pool: int = 0


# ── 评价 ──

class ReviewCreateRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="1-5 星")
    comment: str | None = Field(None, max_length=255)


class OrderReviewResponse(BaseModel):
    id: int
    order_id: int
    application_id: int
    teacher_id: int
    rating: int
    comment: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime | None = None

    model_config = {"from_attributes": True}


# ── 教员费用结算 ──

class TeacherFeeSummaryResponse(BaseModel):
    """教员视角的费用汇总：信息费为教员支出。"""
    total_paid: float = 0      # 累计支付（定金 + 尾款）
    total_refunded: float = 0  # 累计已退
    total_forfeit: float = 0   # 累计被没收
    records: list[FinancialRecordResponse]


# ── 老板端经营看板 ──

class OwnerFunnelStats(BaseModel):
    applications_total: int = 0
    shortlisted: int = 0
    deposit_paid: int = 0
    completed: int = 0


class OwnerTenantRankItem(BaseModel):
    tenant_id: int
    tenant_name: str
    invite_code: str
    is_active: bool
    orders_total: int
    orders_recruiting: int
    orders_completed: int
    applications_total: int
    gmv: float


class OwnerStatsResponse(BaseModel):
    tenant_count: int
    active_tenant_count: int
    teacher_count: int
    banned_teacher_count: int = 0
    orders_recruiting: int
    orders_trial: int
    orders_completed: int
    orders_archived: int
    gmv_total: float
    refund_total: float
    forfeit_total: float
    funnel: OwnerFunnelStats
    ranking: list[OwnerTenantRankItem]


# ── 中介教员管理 ──

class BlacklistCreateRequest(BaseModel):
    reason: str | None = Field(None, max_length=255)


class MyTeacherItem(BaseModel):
    """中介视角的教员档案：与本租户发生过投递关系的教员。"""

    teacher_id: int
    name: str
    phone: str
    school: str | None = None
    gender: Gender
    applications_total: int
    completed_count: int
    violation_count: int
    avg_rating: float | None = None
    is_blacklisted: bool = False
    last_applied_at: datetime.datetime | None = None


class BlacklistItem(BaseModel):
    teacher_id: int
    name: str
    phone: str
    reason: str | None
    created_at: datetime.datetime


# ── OpenAPI 契约补齐（PLAN P0-6）：以下与既有路由的返回体逐字段对齐 ──


class OrderListItem(BaseModel):
    """GET /orders/ 列表项：教员视角坐标降精度，B 端保留精确坐标。"""

    id: int
    raw_id: str
    grade_subject: str
    price_total: str
    base_price: float
    fuzzy_address: str
    status: OrderStatus
    needs_manual_price: bool
    calculated_info_fee: float
    deposit_amount: float
    balance_amount: float
    weekly_frequency: int
    lng: float
    lat: float
    created_at: str | None = None
    expired_at: str | None = None


class OrderListResponse(BaseModel):
    items: list[OrderListItem]
    page: int
    page_size: int
    total: int


class ApplicationSummaryResponse(BaseModel):
    total_applications: int
    order_counts: dict[str, int]


class NotificationItem(BaseModel):
    id: int
    title: str
    content: str | None = None
    application_id: int | None = None
    order_id: int | None = None
    created_at: datetime.datetime
    is_read: bool


class NotificationListResponse(BaseModel):
    unread_count: int
    items: list[NotificationItem]


class MarkedResponse(BaseModel):
    marked: int


class MeResponse(BaseModel):
    sub: str
    role: str
    tenant_id: int | None = None


class DetailResponse(BaseModel):
    detail: str


class OkResponse(BaseModel):
    ok: bool


class BlacklistStatusItem(BaseModel):
    tenant_id: int
    tenant_name: str
    reason: str | None = None
    created_at: datetime.datetime


class AuditLogItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    tenant_id: int | None = None
    actor_role: str
    actor_id: int
    action: str
    object_type: str
    object_id: int
    ip: str | None = None
    created_at: datetime.datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogItem]
    page: int
    page_size: int
    total: int
