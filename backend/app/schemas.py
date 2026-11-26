"""通用接口契约；模块字段由领域服务持有，不再为每个模块复制一份模型类。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class ActionPayload(BaseModel):
    action: str
    remark: str | None = None


class PeriodClosePayload(BaseModel):
    remark: str | None = None


class RefundPayload(BaseModel):
    receipt_no: str
    charge_no: str
    amount: float = Field(gt=0)
    arrival_period: str | None = None


class ReservationClaimPayload(BaseModel):
    remark: str | None = None
