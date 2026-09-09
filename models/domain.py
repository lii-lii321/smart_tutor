import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DECIMAL, Enum,
    TIMESTAMP, ForeignKey, Index, UniqueConstraint, func,
)
from sqlalchemy.orm import relationship
from database import Base


class Gender(str, enum.Enum):
    male = "male"
    female = "female"


class OrderStatus(str, enum.Enum):
    # 唯一事实来源：订单状态由投递流程派生（见 routers/v1/applications.py）
    # recruiting（招聘中）→ trial_in_progress（试课中，须先付定金）→ completed（成交）
    # 任意活跃状态可 → archived（归档）；试课失败/取消可 → recruiting（重新开放）
    recruiting = "recruiting"
    trial_in_progress = "trial_in_progress"
    completed = "completed"
    archived = "archived"

    # 以下状态已废弃，仅为兼容历史数据库行保留定义，不允许再写入。
    # 历史数据由 database.init_db 迁移为上面的活跃状态。
    pending_deposit = "pending_deposit"  # deprecated（候选阶段不再单独占状态，订单保持招聘中）
    pending_approval = "pending_approval"  # deprecated
    pending_balance = "pending_balance"  # deprecated


class ApplicationStatus(str, enum.Enum):
    pending = "pending"
    shortlisted = "shortlisted"
    trial_in_progress = "trial_in_progress"
    deposit_paid = "deposit_paid"
    balance_paid = "balance_paid"
    completed = "completed"
    rejected = "rejected"
    refunded = "refunded"
    # 试课失败/教员违约导致定金被没收：独立于"已拒绝"的终态，
    # 保证已收款项的处置结果与普通落选在状态上可区分（与台账没收流水对应）
    forfeited = "forfeited"


class FinancialType(str, enum.Enum):
    deposit_in = "deposit_in"
    balance_in = "balance_in"
    refund_out = "refund_out"
    forfeit = "forfeit"


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_name = Column(String(50), nullable=False, comment="中介/机构名称")
    invite_code = Column(String(20), unique=True, nullable=False, comment="专属邀请码")
    contact_wechat = Column(String(50), nullable=False, comment="中介联系微信号")
    is_active = Column(Boolean, default=True, nullable=False, comment="是否启用")
    password_hash = Column(String(100), comment="后台登录密码哈希（bcrypt）")
    token_valid_after = Column(TIMESTAMP, nullable=True, comment="早于该时间签发的 token 一律失效")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    orders = relationship("Order", back_populates="tenant", lazy="dynamic")
    applications = relationship("Application", back_populates="tenant", lazy="dynamic")
    financial_records = relationship("FinancialRecord", back_populates="tenant", lazy="dynamic")


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    openid = Column(String(64), unique=True, nullable=False, comment="微信 OpenID")
    name = Column(String(20), nullable=False, comment="教员姓名")
    gender = Column(Enum(Gender), nullable=False, comment="性别")
    phone = Column(String(15), nullable=False, unique=True, comment="手机号")
    wechat_id = Column(String(50), nullable=False, comment="微信号")
    school = Column(String(50), nullable=False, comment="毕业/就读院校")
    is_985_211 = Column(Boolean, default=False, comment="是否 985/211")
    is_985 = Column(Boolean, default=False, comment="是否 985 院校")
    is_211 = Column(Boolean, default=False, comment="是否 211 院校")
    is_double_first_class = Column(Boolean, default=False, comment="是否双一流院校")
    major = Column(String(50), comment="专业")
    grade = Column(String(20), comment="年级")
    highlights = Column(Text, comment="优势标签")
    password_hash = Column(String(100), comment="登录密码哈希（bcrypt），未设置时仅可用微信登录")
    is_banned = Column(Boolean, default=False, nullable=False, comment="是否被平台封禁投递")
    token_valid_after = Column(TIMESTAMP, nullable=True, comment="早于该时间签发的 token 一律失效")
    lng = Column(DECIMAL(10, 6), comment="常驻地经度")
    lat = Column(DECIMAL(10, 6), comment="常驻地纬度")
    home_area = Column(String(100), comment="常驻地描述（如：成都·武侯区），用于展示与地理编码")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    applications = relationship("Application", back_populates="teacher", lazy="dynamic")
    financial_records = relationship("FinancialRecord", back_populates="teacher", lazy="dynamic")
    resumes = relationship("TeacherResume", back_populates="teacher", lazy="dynamic")


class TeacherResume(Base):
    __tablename__ = "teacher_resumes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    title = Column(String(50), nullable=False, comment="简历名称")
    teaching_subjects = Column(String(120), nullable=False, comment="可授科目")
    teaching_grades = Column(String(120), nullable=False, comment="可授年级")
    experience = Column(Text, nullable=False, comment="家教经历")
    strengths = Column(Text, comment="个人优势")
    availability = Column(String(120), comment="可授课时间")
    expected_rate = Column(String(50), comment="期望课酬")
    is_default = Column(Boolean, default=False, comment="默认简历")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    teacher = relationship("Teacher", back_populates="resumes")
    applications = relationship("Application", back_populates="resume", lazy="dynamic")

    __table_args__ = (
        Index("idx_teacher_resume", "teacher_id"),
    )


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, comment="归属租户 ID")
    raw_id = Column(String(50), nullable=False, comment="上游原始编号")
    raw_text = Column(Text, nullable=False, comment="原始微信聊天文本")
    grade_subject = Column(String(50), nullable=False, comment="年级科目")
    requirements = Column(Text, comment="教员要求")
    price_total = Column(String(50), nullable=False, comment="原始课酬文本")
    base_price = Column(DECIMAL(8, 2), nullable=False, comment="单次标准课酬")

    weekly_frequency = Column(Integer, default=1, comment="每周上课次数")
    is_summer_vacation = Column(Boolean, default=False, comment="是否寒暑假单")

    calculated_info_fee = Column(DECIMAL(8, 2), nullable=False, comment="全额信息费")
    deposit_amount = Column(DECIMAL(8, 2), default=100.00, comment="锁定定金")
    balance_amount = Column(DECIMAL(8, 2), nullable=False, comment="需补齐尾款")

    exact_address = Column(String(255), comment="真实门牌号与联系方式（尾款解锁）")
    parent_phone = Column(String(20), comment="家长联系电话（尾款解锁）")
    fuzzy_address = Column(String(100), nullable=False, comment="模糊展示地址")
    subway_remark = Column(String(100), comment="交通补丁")
    lng = Column(DECIMAL(10, 6), nullable=False, comment="订单地理编码经度，不做人工偏移")
    lat = Column(DECIMAL(10, 6), nullable=False, comment="订单地理编码纬度，不做人工偏移")

    status = Column(
        Enum(OrderStatus), default=OrderStatus.recruiting, comment="订单状态"
    )
    selected_teacher_id = Column(Integer, nullable=True, comment="当前被选中的教员 ID")
    expired_at = Column(TIMESTAMP, nullable=False, comment="过期时间")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    tenant = relationship("Tenant", back_populates="orders")
    applications = relationship("Application", back_populates="order", lazy="dynamic")

    __table_args__ = (
        Index("idx_tenant_status", "tenant_id", "status"),
        Index("idx_raw_id", "raw_id"),
        # 过期扫描：scheduler 归档 + 即将过期提醒 + 教员列表按到期排序都走这两个条件
        Index("idx_status_expired", "status", "expired_at"),
        UniqueConstraint("tenant_id", "raw_id", name="uk_tenant_raw"),
    )


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    resume_id = Column(Integer, ForeignKey("teacher_resumes.id"), nullable=True)

    status = Column(
        Enum(ApplicationStatus), default=ApplicationStatus.pending, comment="投递状态"
    )
    proposed_price = Column(DECIMAL(8, 2), nullable=True, comment="教员报价（自带价订单时填写）")
    applied_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    shortlisted_at = Column(TIMESTAMP, nullable=True, comment="被选中时间")
    deposit_paid_at = Column(TIMESTAMP, nullable=True, comment="支付定金时间")
    balance_paid_at = Column(TIMESTAMP, nullable=True, comment="补齐尾款时间")
    rejected_at = Column(TIMESTAMP, nullable=True, comment="被拒时间")
    refunded_at = Column(TIMESTAMP, nullable=True, comment="退款时间")

    order = relationship("Order", back_populates="applications")
    teacher = relationship("Teacher", back_populates="applications")
    resume = relationship("TeacherResume", back_populates="applications")
    tenant = relationship("Tenant", back_populates="applications")

    __table_args__ = (
        UniqueConstraint("teacher_id", "order_id", name="uk_teacher_order"),
        # 订单维度的状态守卫（资金检查/投递列表）与租户维度待审统计的高频过滤
        Index("idx_app_order_status", "order_id", "status"),
        Index("idx_app_tenant_status", "tenant_id", "status"),
    )


class FinancialRecord(Base):
    __tablename__ = "financial_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)

    amount = Column(DECIMAL(8, 2), nullable=False, comment="涉及金额")
    type = Column(Enum(FinancialType), nullable=False, comment="交易类型")
    remark = Column(String(255))
    operator_role = Column(String(20), comment="登记人角色：tenant_admin/super_admin/teacher")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    tenant = relationship("Tenant", back_populates="financial_records")
    teacher = relationship("Teacher", back_populates="financial_records")

    __table_args__ = (
        Index("idx_fin_tenant_created", "tenant_id", "created_at"),
        Index("idx_fin_teacher", "teacher_id"),
    )


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=True, comment="C 端接收教员")
    tenant_id = Column(Integer, nullable=True, comment="B 端接收租户（与 teacher_id 二选一）")
    title = Column(String(50), nullable=False, comment="通知标题")
    content = Column(String(255), comment="通知正文")
    application_id = Column(Integer, comment="关联投递，可空")
    order_id = Column(Integer, comment="关联订单，可空")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    read_at = Column(TIMESTAMP, nullable=True, comment="已读时间")

    __table_args__ = (
        Index("idx_notification_teacher", "teacher_id", "read_at"),
        Index("idx_notification_tenant", "tenant_id", "read_at"),
        Index("idx_notification_order", "order_id"),
    )


class OrderReview(Base):
    """中介对成交教员的评价：一单一评，进教员信用与推荐分。"""

    __tablename__ = "order_reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, unique=True)
    application_id = Column(Integer, nullable=False, comment="成交的投递")
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    rating = Column(Integer, nullable=False, comment="评分 1-5 星")
    comment = Column(String(255), comment="评语")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    __table_args__ = (
        Index("idx_order_review_teacher", "teacher_id"),
    )


class TenantTeacherBlacklist(Base):
    """中介级教员黑名单：仅限制本租户，全局封禁仍是平台老板的权限。"""

    __tablename__ = "tenant_teacher_blacklist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    reason = Column(String(255), comment="拉黑原因")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    __table_args__ = (
        UniqueConstraint("tenant_id", "teacher_id", name="uk_tenant_teacher_black"),
        Index("idx_blacklist_tenant", "tenant_id"),
    )
