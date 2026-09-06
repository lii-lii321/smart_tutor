import csv
import datetime
import io
from decimal import Decimal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from middleware.auth import TokenPayload, require_tenant_owner
from models.domain import FinancialRecord, FinancialType
from models.schemas import FinancialRecordResponse, FinancialSummaryResponse

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
    query = select(FinancialRecord)
    if payload.role != "super_admin":
        query = query.where(FinancialRecord.tenant_id == payload.tenant_id)
    query = _apply_filters(query, type, start_date, end_date)

    query = query.order_by(FinancialRecord.created_at.desc(), FinancialRecord.id.desc())
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    records = result.scalars().all()

    all_result = await db.execute(query)
    totals = {
        FinancialType.deposit_in.value: Decimal("0"),
        FinancialType.balance_in.value: Decimal("0"),
        FinancialType.refund_out.value: Decimal("0"),
        FinancialType.forfeit.value: Decimal("0"),
    }
    for record in all_result.scalars().all():
        totals[record.type.value] += record.amount

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
        records=[_build_record(r) for r in records],
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
    query = select(FinancialRecord)
    if payload.role != "super_admin":
        query = query.where(FinancialRecord.tenant_id == payload.tenant_id)
    query = _apply_filters(query, type, start_date, end_date)
    query = query.order_by(FinancialRecord.created_at.asc(), FinancialRecord.id.asc())

    result = await db.execute(query)
    records = result.scalars().all()

    buffer = io.StringIO()
    buffer.write("\ufeff")  # UTF-8 BOM：避免 Excel 打开中文乱码
    writer = csv.writer(buffer)
    writer.writerow(["记录ID", "时间", "类型", "金额", "订单ID", "教员ID", "备注"])
    for record in records:
        writer.writerow([
            record.id,
            record.created_at.strftime("%Y-%m-%d %H:%M:%S") if record.created_at else "",
            _TYPE_LABELS.get(record.type, record.type.value),
            f"{record.amount:.2f}",
            record.order_id,
            record.teacher_id,
            record.remark or "",
        ])

    filename = f"financial-records-{datetime.date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _build_record(record: FinancialRecord) -> FinancialRecordResponse:
    return FinancialRecordResponse.model_validate(
        {
            "id": record.id,
            "order_id": record.order_id,
            "tenant_id": record.tenant_id,
            "teacher_id": record.teacher_id,
            "amount": float(record.amount),
            "type": record.type.value,
            "remark": record.remark,
            "created_at": record.created_at,
        }
    )
