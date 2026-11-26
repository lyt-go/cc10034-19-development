"""周期结算专用 API：关账、退款归期、回执追查、旧预约领取配置。

通用列表/登记/动作仍走 resource 路由（/api/budget_period 等），
本路由只承载跨表状态流转，必须先于通用资源路由注册。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.schemas import (
    ActionResult,
    PeriodClosePayload,
    RefundPayload,
    ReservationClaimPayload,
)
from app.services.budget_cycle import budget_cycle_service
from app.services import service_for

router = APIRouter(prefix="/api/budget-cycle", tags=["周期结算"])


@router.post("/periods/{period_id}/close", response_model=ActionResult)
def close_period(period_id: int, payload: PeriodClosePayload) -> ActionResult:
    """管理员提交待关闭账期，服务端生成预算结算单并结转未清预约。"""
    settlement, message = budget_cycle_service.submit_close(period_id)
    return ActionResult(ok=settlement is not None, message=message, entry=settlement)


@router.post("/refunds", response_model=ActionResult)
def apply_refund(payload: RefundPayload) -> ActionResult:
    """提交退款回执；重复回执幂等，额度按费用原账期归期。"""
    refund, message = budget_cycle_service.apply_refund(
        receipt_no=payload.receipt_no,
        charge_no=payload.charge_no,
        amount=payload.amount,
        arrival_period=payload.arrival_period or "",
    )
    return ActionResult(ok=refund is not None, message=message, entry=refund)


@router.get("/refunds/{receipt_no}/trace")
def trace_refund(receipt_no: str) -> dict[str, Any]:
    """追查一笔退款额度进入了哪个账期，确认没有跨账期重复增加余额。"""
    result = budget_cycle_service.trace_receipt(receipt_no)
    if result is None:
        return {"receipt_no": receipt_no, "found": False}
    return {"receipt_no": receipt_no, "found": True, **result}


@router.get("/reservations/{reservation_id}/eligibility")
def reservation_eligibility(reservation_id: int) -> dict[str, Any]:
    """旧预约领取噪声配置前的资格查询（只读）。"""
    return budget_cycle_service.reservation_eligibility(reservation_id)


@router.post("/reservations/{reservation_id}/claim", response_model=ActionResult)
def claim_reservation(reservation_id: int, payload: ReservationClaimPayload) -> ActionResult:
    """旧预约正式领取噪声配置，按额度来源扣减账期余额或结算单结转额度。"""
    reservation, message = budget_cycle_service.claim_reservation(reservation_id)
    return ActionResult(ok=reservation is not None, message=message, entry=reservation)


@router.get("/noise-engine/reservations/{reservation_id}/check")
def noise_engine_check(reservation_id: int) -> dict[str, Any]:
    """噪声引擎侧闸门：判断关联旧预约当前还能否领取配置。"""
    service = service_for("noise_engine")
    return service.check_reservation(reservation_id)
