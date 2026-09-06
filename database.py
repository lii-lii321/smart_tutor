import os
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from config import settings

_engine = None
_async_sessionmaker = None

# SQLite 文件路径（开发默认）
DEFAULT_SQLITE_PATH = os.path.join(os.path.dirname(__file__), "dev.db")
DEFAULT_DB_URL = f"sqlite+aiosqlite:///{DEFAULT_SQLITE_PATH}"


def _get_database_url() -> str:
    if settings.DATABASE_URL:
        return settings.DATABASE_URL
    if settings.DEV_MODE:
        return DEFAULT_DB_URL
    if settings.DB_PASSWORD is not None:
        return (
            f"mysql+aiomysql://{settings.DB_USER}:{settings.DB_PASSWORD}"
            f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}?charset=utf8mb4"
        )
    raise RuntimeError('生产环境必须配置 MySQL DATABASE_URL 或 DB_* 连接参数')


def _get_engine():
    global _engine
    if _engine is None:
        url = _get_database_url()
        is_sqlite = url.startswith("sqlite")
        engine_kwargs = {"echo": False}
        if is_sqlite:
            engine_kwargs.update(
                poolclass=NullPool,
                connect_args={"check_same_thread": False},
            )
        else:
            engine_kwargs.update(
                pool_size=20,
                max_overflow=10,
                pool_pre_ping=True,
                pool_recycle=1800,
                # 统一 MySQL 会话时区为 UTC：server_default CURRENT_TIMESTAMP 与
                # 应用层 datetime.utcnow() 写入同一时区，按日对账不再错位 8 小时
                connect_args={"init_command": "SET time_zone = '+00:00'"},
            )
        _engine = create_async_engine(url, **engine_kwargs)
    return _engine


def _get_sessionmaker():
    global _async_sessionmaker
    if _async_sessionmaker is None:
        _async_sessionmaker = async_sessionmaker(
            _get_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _async_sessionmaker


class Base(DeclarativeBase):
    pass


async def get_db():
    sessionmaker = _get_sessionmaker()
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def _ensure_raw_text_column(sync_conn):
            inspector = inspect(sync_conn)
            columns = {col["name"] for col in inspector.get_columns("orders")}
            if "raw_text" not in columns:
                sync_conn.execute(text("ALTER TABLE orders ADD COLUMN raw_text TEXT"))
                try:
                    sync_conn.execute(
                        text("UPDATE orders SET raw_text = COALESCE(raw_id, '') WHERE raw_text IS NULL")
                    )
                except Exception:
                    pass

        await conn.run_sync(_ensure_raw_text_column)

        def _ensure_resume_columns(sync_conn):
            inspector = inspect(sync_conn)
            tables = set(inspector.get_table_names())
            if "applications" not in tables:
                return
            columns = {col["name"] for col in inspector.get_columns("applications")}
            if "resume_id" not in columns:
                sync_conn.execute(text("ALTER TABLE applications ADD COLUMN resume_id INTEGER"))

        await conn.run_sync(_ensure_resume_columns)

        def _ensure_teacher_school_tag_columns(sync_conn):
            inspector = inspect(sync_conn)
            tables = set(inspector.get_table_names())
            if "teachers" not in tables:
                return
            columns = {col["name"] for col in inspector.get_columns("teachers")}
            additions = {
                "is_985": "ALTER TABLE teachers ADD COLUMN is_985 BOOLEAN DEFAULT 0",
                "is_211": "ALTER TABLE teachers ADD COLUMN is_211 BOOLEAN DEFAULT 0",
                "is_double_first_class": (
                    "ALTER TABLE teachers ADD COLUMN is_double_first_class BOOLEAN DEFAULT 0"
                ),
            }
            for column, statement in additions.items():
                if column not in columns:
                    sync_conn.execute(text(statement))
            if "is_985_211" in columns:
                sync_conn.execute(
                    text(
                        "UPDATE teachers SET is_985 = 1, is_211 = 1 "
                        "WHERE is_985_211 = 1 AND is_985 = 0 AND is_211 = 0"
                    )
                )

        await conn.run_sync(_ensure_teacher_school_tag_columns)

        def _ensure_tenant_active_column(sync_conn):
            inspector = inspect(sync_conn)
            tables = set(inspector.get_table_names())
            if "tenants" not in tables:
                return
            columns = {col["name"] for col in inspector.get_columns("tenants")}
            if "is_active" not in columns:
                sync_conn.execute(
                    text("ALTER TABLE tenants ADD COLUMN is_active BOOLEAN DEFAULT 1 NOT NULL")
                )

        await conn.run_sync(_ensure_tenant_active_column)

        def _ensure_password_columns(sync_conn):
            inspector = inspect(sync_conn)
            tables = set(inspector.get_table_names())
            for table in ("teachers", "tenants"):
                if table not in tables:
                    continue
                columns = {col["name"] for col in inspector.get_columns(table)}
                if "password_hash" not in columns:
                    sync_conn.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN password_hash VARCHAR(100)")
                    )

        await conn.run_sync(_ensure_password_columns)

        def _ensure_teacher_banned_column(sync_conn):
            inspector = inspect(sync_conn)
            tables = set(inspector.get_table_names())
            if "teachers" not in tables:
                return
            columns = {col["name"] for col in inspector.get_columns("teachers")}
            if "is_banned" not in columns:
                sync_conn.execute(
                    text("ALTER TABLE teachers ADD COLUMN is_banned BOOLEAN DEFAULT 0 NOT NULL")
                )

        await conn.run_sync(_ensure_teacher_banned_column)

        def _ensure_teachers_phone_unique(sync_conn):
            inspector = inspect(sync_conn)
            tables = set(inspector.get_table_names())
            if "teachers" not in tables:
                return
            uniques = {
                u["name"] for u in inspector.get_unique_constraints("teachers")
            }
            if "uk_teachers_phone" not in uniques:
                # 先清理同号重复账号中无业务的孤儿行；带业务数据的行需人工改号
                sync_conn.execute(
                    text(
                        "DELETE FROM teachers WHERE id IN ("
                        " SELECT t.id FROM teachers t WHERE EXISTS ("
                        "  SELECT 1 FROM teachers t2 WHERE t2.phone = t.phone AND t2.id < t.id"
                        " ) AND NOT EXISTS (SELECT 1 FROM applications a WHERE a.teacher_id = t.id)"
                        " AND NOT EXISTS (SELECT 1 FROM financial_records f WHERE f.teacher_id = t.id)"
                        ")"
                    )
                )
                sync_conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS uk_teachers_phone ON teachers (phone)"
                    )
                )

        await conn.run_sync(_ensure_teachers_phone_unique)

        def _migrate_deprecated_order_statuses(sync_conn):
            """将废弃状态归一化到新状态机：
            pending_deposit（候选占位）→ recruiting（候选阶段订单保持招聘中）
            pending_approval（教员已确认）→ recruiting
            pending_balance（等尾款）→ trial_in_progress（试课中，尾款在试课后确认）
            """
            inspector = inspect(sync_conn)
            tables = set(inspector.get_table_names())
            if "orders" not in tables:
                return
            columns = {col["name"] for col in inspector.get_columns("orders")}
            if "status" not in columns:
                return
            sync_conn.execute(
                text(
                    "UPDATE orders SET status = 'recruiting' "
                    "WHERE status IN ('pending_deposit', 'pending_approval')"
                )
            )
            sync_conn.execute(
                text(
                    "UPDATE orders SET status = 'trial_in_progress' "
                    "WHERE status = 'pending_balance'"
                )
            )

        await conn.run_sync(_migrate_deprecated_order_statuses)


async def seed_demo_data():
    if not settings.DEV_MODE:
        return

    from sqlalchemy import select
    from models.domain import Tenant, Teacher, TeacherResume, Gender
    from services.auth import hash_password

    # 演示账号统一密码，仅 DEV_MODE 播种时使用
    dev_password_hash = hash_password("dev123456")

    sessionmaker = _get_sessionmaker()
    async with sessionmaker() as session:
        sample_tenants = [
            {"tenant_name": "成都壹号教育", "invite_code": "tx886", "contact_wechat": "wx_boss_001", "is_active": True},
            {"tenant_name": "锦江优学", "invite_code": "jj2026", "contact_wechat": "wx_jj_002", "is_active": True},
            {"tenant_name": "蜀都家教", "invite_code": "sd1001", "contact_wechat": "wx_sd_003", "is_active": False},
        ]

        existing_tenants = await session.execute(select(Tenant))
        tenants_by_code = {row.invite_code: row for row in existing_tenants.scalars().all()}
        for item in sample_tenants:
            tenant = tenants_by_code.get(item["invite_code"])
            if tenant is None:
                session.add(Tenant(**item, password_hash=dev_password_hash))
            elif tenant.password_hash is None:
                tenant.password_hash = dev_password_hash

        sample_teachers = [
            {
                "openid": "demo_teacher_001",
                "name": "李老师",
                "gender": Gender.female,
                "phone": "13900000001",
                "wechat_id": "li_teacher_01",
                "school": "四川大学",
                "major": "英语教育",
                "grade": "研二",
                "highlights": "耐心细致，适合低年级启蒙",
                "resume": {
                    "title": "李老师默认简历",
                    "teaching_subjects": "小学英语、初中英语",
                    "teaching_grades": "小一-初二",
                    "experience": "带过多名小学到初中学生，注重基础和口语训练。",
                    "strengths": "互动感强，善于建立学习习惯",
                    "availability": "周末全天",
                    "expected_rate": "180-220/次",
                    "is_default": True,
                },
            },
            {
                "openid": "demo_teacher_002",
                "name": "王老师",
                "gender": Gender.male,
                "phone": "13900000002",
                "wechat_id": "wang_teacher_02",
                "school": "电子科技大学",
                "major": "数学与应用数学",
                "grade": "大四",
                "highlights": "逻辑清晰，擅长提分",
                "resume": {
                    "title": "王老师默认简历",
                    "teaching_subjects": "初中数学、高中数学",
                    "teaching_grades": "初一-高二",
                    "experience": "擅长梳理题型和错题复盘，带过多名提分案例。",
                    "strengths": "讲解条理清楚，适合应试提升",
                    "availability": "工作日晚上、周末",
                    "expected_rate": "220-280/次",
                    "is_default": True,
                },
            },
            {
                "openid": "demo_teacher_003",
                "name": "陈老师",
                "gender": Gender.female,
                "phone": "13900000003",
                "wechat_id": "chen_teacher_03",
                "school": "西南财经大学",
                "major": "物理学",
                "grade": "研一",
                "highlights": "理科基础扎实，善于拆题",
                "resume": {
                    "title": "陈老师默认简历",
                    "teaching_subjects": "高中物理、初中物理",
                    "teaching_grades": "初二-高三",
                    "experience": "长期做一对一家教，注重实验和公式理解。",
                    "strengths": "思路稳，适合拔高和补基础",
                    "availability": "周三晚上、周末",
                    "expected_rate": "240-300/次",
                    "is_default": True,
                },
            },
            {
                "openid": "demo_teacher_004",
                "name": "刘老师",
                "gender": Gender.male,
                "phone": "13900000004",
                "wechat_id": "liu_teacher_04",
                "school": "四川师范大学",
                "major": "汉语言文学",
                "grade": "研三",
                "highlights": "作文和阅读理解强项",
                "resume": {
                    "title": "刘老师默认简历",
                    "teaching_subjects": "语文、作文",
                    "teaching_grades": "小学高年级-初三",
                    "experience": "带过多名语文薄弱学生，擅长阅读与写作。",
                    "strengths": "表达清晰，控节奏稳",
                    "availability": "周二/周四晚上",
                    "expected_rate": "180-260/次",
                    "is_default": True,
                },
            },
        ]

        existing_teachers = await session.execute(select(Teacher))
        teachers_by_openid = {row.openid: row for row in existing_teachers.scalars().all()}
        existing_resumes = await session.execute(
            select(TeacherResume.teacher_id).where(TeacherResume.is_default.is_(True))
        )
        resume_teacher_ids = {row[0] for row in existing_resumes.all()}

        for item in sample_teachers:
            existing = teachers_by_openid.get(item["openid"])
            if existing is not None:
                if existing.password_hash is None:
                    existing.password_hash = dev_password_hash
                continue
            teacher = Teacher(
                openid=item["openid"],
                name=item["name"],
                gender=item["gender"],
                phone=item["phone"],
                password_hash=dev_password_hash,
                wechat_id=item["wechat_id"],
                school=item["school"],
                major=item["major"],
                grade=item["grade"],
                highlights=item["highlights"],
                is_985_211=True,
                is_985=True,
                is_211=False,
                is_double_first_class=True,
            )
            session.add(teacher)
            await session.flush()
            if teacher.id not in resume_teacher_ids:
                session.add(TeacherResume(teacher_id=teacher.id, **item["resume"]))

        await session.commit()
