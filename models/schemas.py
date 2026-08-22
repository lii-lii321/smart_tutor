from __future__ import annotations
import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator
from models.domain import OrderStatus, ApplicationStatus, Gender


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
    lng: float | None = None
    lat: float | None = None

    model_config = {"from_attributes": True}


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

    model_config = {"from_attributes": True}


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


class OwnerLoginRequest(BaseModel):
    access_code: str = Field(..., min_length=1, max_length=50)


class TenantLoginRequest(BaseModel):
    invite_code: str = Field(..., min_length=1, max_length=20)

    @field_validator("invite_code")
    @classmethod
    def valid_invite_code(cls, v: str) -> str:
        return v.strip()


class TenantBrief(BaseModel):
    id: int
    tenant_name: str
    invite_code: str

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

    @field_validator("invite_code")
    @classmethod
    def normalize_invite_code(cls, v: str | None) -> str | None:
        return v.strip() if v else v


class TenantStatusUpdate(BaseModel):
    is_active: bool


class TenantAdminResponse(BaseModel):
    id: int
    tenant_name: str
    invite_code: str
    contact_wechat: str
    is_active: bool
    created_at: datetime.datetime

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
    raw_text: str = Field(..., min_length=1, description="微信聊天复制文本")


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


class BatchParseResponse(BaseModel):
    items: list[ParsedOrderItem]
    count: int


# ── 订单导入 ──

class OrderImportItem(BaseModel):
    raw_id: str
    raw_text: str
    grade_subject: str
    requirements: str | None = ""
    price_total: str
    base_price: float
    weekly_frequency: int = 1
    is_summer_vacation: bool = False
    exact_address: str | None = None
    parent_phone: str | None = None
    subway_remark: str | None = None
    fuzzy_address: str
    lng: float
    lat: float
    calculated_info_fee: float
    deposit_amount: float
    balance_amount: float

    @field_validator("base_price", "calculated_info_fee", "deposit_amount", "balance_amount")
    @classmethod
    def positive(cls, v: float) -> float:
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
    base_price: float | None = None
    weekly_frequency: int | None = Field(None, ge=1, le=14)
    is_summer_vacation: bool | None = None
    exact_address: str | None = Field(None, max_length=255)
    parent_phone: str | None = Field(None, max_length=20)
    fuzzy_address: str | None = Field(None, min_length=1, max_length=100)
    subway_remark: str | None = Field(None, max_length=100)
    lng: float | None = None
    lat: float | None = None
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
    is_summer_vacation: bool = False
    status: OrderStatus
    expired_at: datetime.datetime


class AgentBoardResponse(BaseModel):
    tenant_name: str
    invite_code: str
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

class ApplicationRequest(BaseModel):
    order_id: int
    teacher_id: int
    proposed_price: float | None = None  # 教员报价，自带价订单时填写
    resume_id: int | None = None


class ApplicationResponse(BaseModel):
    id: int
    order_id: int
    teacher_id: int
    tenant_id: int
    resume_id: int | None = None
    resume: TeacherResumeResponse | None = None
    teacher: TeacherSummary | None = None
    status: ApplicationStatus
    proposed_price: float | None = None
    applied_at: datetime.datetime
    shortlisted_at: datetime.datetime | None
    deposit_paid_at: datetime.datetime | None
    balance_paid_at: datetime.datetime | None

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
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class FinancialSummaryResponse(BaseModel):
    deposit_in: float = 0
    balance_in: float = 0
    refund_out: float = 0
    forfeit: float = 0
    net_amount: float = 0
    records: list[FinancialRecordResponse]
