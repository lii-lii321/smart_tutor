from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from middleware.auth import TokenPayload, require_tenant_owner
from models.domain import FinancialRecord, FinancialType
from models.schemas import FinancialRecordResponse, FinancialSummaryResponse

router = APIRouter(prefix="/api/v1/financial-records", tags=["财务"])


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


@router.get("/", response_model=FinancialSummaryResponse)
async def list_financial_records(
    page: int = 1,
    page_size: int = 50,
    payload: TokenPayload = Depends(require_tenant_owner()),
    db: AsyncSession = Depends(get_db),
):
    query = select(FinancialRecord)
    if payload.role != "super_admin":
        query = query.where(FinancialRecord.tenant_id == payload.tenant_id)

    query = query.order_by(FinancialRecord.created_at.desc())
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

    net_amount = (
        totals[FinancialType.deposit_in.value]
        + totals[FinancialType.balance_in.value]
        + totals[FinancialType.forfeit.value]
        - totals[FinancialType.refund_out.value]
    )

    return FinancialSummaryResponse(
        deposit_in=float(totals[FinancialType.deposit_in.value]),
        balance_in=float(totals[FinancialType.balance_in.value]),
        refund_out=float(totals[FinancialType.refund_out.value]),
        forfeit=float(totals[FinancialType.forfeit.value]),
        net_amount=float(net_amount),
        records=[_build_record(record) for record in records],
    )
