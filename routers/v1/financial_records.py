import csv
import datetime
import io
from decimal import Decimal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from middleware.auth import TokenPayload, require_role, require_tenant_owner
from models.domain import FinancialRecord, FinancialType, Order, Teacher
from models.schemas import (
    FinancialRecordResponse,
    FinancialSummaryResponse,
    TeacherFeeSummaryResponse,
)

router = APIRouter(prefix="/api/v1/financial-records", tags=["财务"])

_TYPE_LABELS = {
    FinancialType.deposit_in: "定金收入",
    FinancialType.balance_in: "尾款收入",
    FinancialType.refund_out: "退款支出",
    FinancialType.forfeit: "定金没收",
}


def _apply_filters(
    query,
    record_type: FinancialType | None,
    start_date: datetime.date | None,
    end_date: datetime.date | None,
):
    """列表与导出共用的筛选逻辑；日期按自然日（含 end_date 当天）。"""
    if record_type is not None:
        query = query.where(FinancialRecord.type == record_type)
    if start_date is not None:
        query = query.where(FinancialRecord.created_at >= start_date)
    if end_date is not None:
        query = query.where(FinancialRecord.created_at < end_date + datetime.timedelta(days=1))
    return query


@router.get("/", response_model=FinancialSummaryResponse)
async def list_financial_records(
    type: FinancialType | None = None,
    start_date: datetime.date | None = None,
    end_date: datetime.date | None = None,
    page: int = 1,
    page_size: int = 50,
    payload: TokenPayload = Depends(require_tenant_owner()),
    db: AsyncSession = Depends(get_db),
):
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    # 连带订单科目/原始单号与教员姓名：对账时直接可读，不用猜内部 ID
    query = select(
        FinancialRecord, Order.grade_subject, Order.raw_id, Teacher.name, Teacher.school
    ).join(Order, Order.id == FinancialRecord.order_id).join(Teacher, Teacher.id == FinancialRecord.teacher_id)
    if payload.role != "super_admin":
        query = query.where(FinancialRecord.tenant_id == payload.tenant_id)
    query = _apply_filters(query, type, start_date, end_date)

    query = query.order_by(FinancialRecord.created_at.desc(), FinancialRecord.id.desc())
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    rows = result.all()
    records = [_build_record(row[0], row[1], row[2], row[3], row[4]) for row in rows]

    # 汇总口径：仅按日期范围聚合，不随类型筛选收窄——
    # 顶部概览与类型 chip 上的金额始终是"该时间段内四类齐全"的期间汇总
    totals_query = select(
        FinancialRecord.type,
        func.coalesce(func.sum(FinancialRecord.amount), 0).label("total"),
    ).group_by(FinancialRecord.type)
    if payload.role != "super_admin":
        totals_query = totals_query.where(FinancialRecord.tenant_id == payload.tenant_id)
    totals_query = _apply_filters(totals_query, None, start_date, end_date)
    totals = {t.value: Decimal("0") for t in FinancialType}
    for record_type, total in (await db.execute(totals_query)).all():
        totals[record_type.value] = Decimal(str(total))

    # 没收（forfeit）只是资金性质标注：该笔钱在确认定金时已计入 deposit_in，
    # 不再重复计入净额——否则教员违约没收会让净收入翻倍、与实收现金对不上。
    net_amount = (
        totals[FinancialType.deposit_in.value]
        + totals[FinancialType.balance_in.value]
        - totals[FinancialType.refund_out.value]
    )

    return FinancialSummaryResponse(
        deposit_in=float(totals[FinancialType.deposit_in.value]),
        balance_in=float(totals[FinancialType.balance_in.value]),
        refund_out=float(totals[FinancialType.refund_out.value]),
        forfeit=float(totals[FinancialType.forfeit.value]),
        net_amount=float(net_amount),
        records=records,
    )


@router.get("/mine/export")
async def export_my_fees(
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    """教员导出自己的费用结算单（CSV，UTF-8 BOM）。"""
    result = await db.execute(
        select(FinancialRecord)
        .where(FinancialRecord.teacher_id == payload.teacher_id)
        .order_by(FinancialRecord.created_at.asc(), FinancialRecord.id.asc())
    )
    records = result.scalars().all()

    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(["时间", "类型", "金额", "订单ID", "备注"])
    for record in records:
        writer.writerow([
            record.created_at.strftime("%Y-%m-%d %H:%M:%S") if record.created_at else "",
            _TYPE_LABELS.get(record.type, record.type.value),
            f"{record.amount:.2f}",
            record.order_id,
            record.remark or "",
        ])

    filename = f"my-fees-{datetime.date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export")
async def export_financial_records(
    type: FinancialType | None = None,
    start_date: datetime.date | None = None,
    end_date: datetime.date | None = None,
    payload: TokenPayload = Depends(require_tenant_owner()),
    db: AsyncSession = Depends(get_db),
):
    """按当前筛选条件导出 CSV（UTF-8 BOM，Excel 可直接打开）。"""
    query = select(
        FinancialRecord, Order.grade_subject, Order.raw_id, Teacher.name
    ).join(Order, Order.id == FinancialRecord.order_id).join(Teacher, Teacher.id == FinancialRecord.teacher_id)
    if payload.role != "super_admin":
        query = query.where(FinancialRecord.tenant_id == payload.tenant_id)
    query = _apply_filters(query, type, start_date, end_date)
    query = query.order_by(FinancialRecord.created_at.asc(), FinancialRecord.id.asc())

    result = await db.execute(query)
    rows = result.all()

    buffer = io.StringIO()
    buffer.write("\ufeff")  # UTF-8 BOM：避免 Excel 打开中文乱码
    writer = csv.writer(buffer)
    writer.writerow(["记录ID", "时间", "类型", "金额", "订单ID", "订单科目", "原始单号", "教员ID", "教员姓名", "备注"])
    for row in rows:
        record, subject, raw_id, teacher_name = row[0], row[1], row[2], row[3]
        writer.writerow([
            record.id,
            record.created_at.strftime("%Y-%m-%d %H:%M:%S") if record.created_at else "",
            _TYPE_LABELS.get(record.type, record.type.value),
            f"{record.amount:.2f}",
            record.order_id,
            subject or "",
            raw_id or "",
            record.teacher_id,
            teacher_name or "",
            record.remark or "",
        ])

    filename = f"financial-records-{datetime.date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _build_record(
    record: FinancialRecord,
    order_subject: str | None = None,
    order_raw_id: str | None = None,
    teacher_name: str | None = None,
    teacher_school: str | None = None,
) -> FinancialRecordResponse:
    return FinancialRecordResponse.model_validate(
        {
            "id": record.id,
            "order_id": record.order_id,
            "tenant_id": record.tenant_id,
            "teacher_id": record.teacher_id,
            "amount": float(record.amount),
            "type": record.type.value,
            "remark": record.remark,
            "operator_role": record.operator_role,
            "created_at": record.created_at,
            "order_subject": order_subject,
            "order_raw_id": order_raw_id,
            "teacher_name": teacher_name,
            "teacher_school": teacher_school,
            "raw_order_id": order_raw_id,  # 教员端结算单历史字段名，保持兼容
        }
    )


@router.get("/mine", response_model=TeacherFeeSummaryResponse)
async def my_fees(
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    """教员结算单：我的费用流水与汇总（信息费为教员支出）。"""
    result = await db.execute(
        select(
            FinancialRecord, Order.raw_id, Order.grade_subject, Teacher.name, Teacher.school
        )
        .join(Order, Order.id == FinancialRecord.order_id)
        .join(Teacher, Teacher.id == FinancialRecord.teacher_id)
        .where(FinancialRecord.teacher_id == payload.teacher_id)
        .order_by(FinancialRecord.created_at.desc(), FinancialRecord.id.desc())
    )
    rows = result.all()

    totals = {t: Decimal("0") for t in FinancialType}
    for row in rows:
        totals[row[0].type] += row[0].amount

    return TeacherFeeSummaryResponse(
        total_paid=float(totals[FinancialType.deposit_in] + totals[FinancialType.balance_in]),
        total_refunded=float(totals[FinancialType.refund_out]),
        total_forfeit=float(totals[FinancialType.forfeit]),
        records=[_build_record(r[0], r[2], r[1], r[3], r[4]) for r in rows],
    )
