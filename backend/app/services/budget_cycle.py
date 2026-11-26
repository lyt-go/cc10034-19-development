"""周期结算领域服务：账期关闭、退款归期、旧预约领取资格的全部状态流转。

设计不变量（测试与页面都围绕这些规则核对）：
1. 已执行费用永远保留在原账期，关账不改动任何 budget_charge 的账期归属。
2. 结算时按「已执行费用 + 未清预约」生成预算结算单；未清预约结转，额度来源
   明确指向该结算单，旧账期可用余额清零，未被预约占用的剩余额度不进入新账期。
3. 退款按回执编号幂等：重复回执只返回首条记录，不会在任何账期重复增加余额。
4. 退款跟随费用的原账期归期：原账期已关闭时，计入该账期结算单的关账后退款
   累计与关账后净额，绝不记入退款到达时所在的新账期余额。
5. 旧预约能否领取噪声配置只看它自己的额度来源：开放账期看可用余额，已关闭
   账期看结算单结转剩余；领取后对应来源立即扣减，可追溯。
"""
from __future__ import annotations

from typing import Any

from app.store import store

_EPS = 4  # Epsilon 统一保留 4 位小数，规避浮点比较误差


def _r(value: float) -> float:
    return round(float(value), _EPS)


class BudgetCycleService:
    """周期结算门面：跨账期/费用/预约/结算单/退款五张表的联动都收敛在这里。"""

    PERIOD = "budget_period"
    CHARGE = "budget_charge"
    RESERVATION = "budget_reservation"
    SETTLEMENT = "budget_settlement"
    REFUND = "budget_refund"

    # ————————————————————————————————————
    # 基础读取
    # ————————————————————————————————————
    def _rows(self, table: str) -> list[dict[str, Any]]:
        return store.rows(table)

    def _find(self, table: str, entry_id: int) -> dict[str, Any] | None:
        return store.find(table, entry_id)

    def _find_by(self, table: str, field: str, value: Any) -> dict[str, Any] | None:
        for row in self._rows(table):
            if str(row.get(field, "")) == str(value):
                return row
        return None

    def _next_id(self, table: str) -> int:
        return max((int(r.get("id", 0)) for r in self._rows(table)), default=0) + 1

    def _period_by_code(self, code: str) -> dict[str, Any] | None:
        return self._find_by(self.PERIOD, "账期编号", code)

    # ————————————————————————————————————
    # 1. 周期关闭：提交待关闭账期 → 生成预算结算单
    # ————————————————————————————————————
    def submit_close(self, period_id: int) -> tuple[dict[str, Any] | None, str]:
        period = self._find(self.PERIOD, period_id)
        if period is None:
            return None, f"预算账期 {period_id} 不存在或已归档"
        if period["status"] == "已关闭":
            return None, f"账期 {period['账期编号']} 已关闭，不能重复关账"

        code = period["账期编号"]
        charges = [c for c in self._rows(self.CHARGE) if c["账期编号"] == code]
        reservations = [
            r for r in self._rows(self.RESERVATION)
            if r["账期编号"] == code and r["status"] in ("待领取", "可领取")
        ]

        used = _r(sum(float(c["Epsilon金额"]) for c in charges))
        reserved = _r(sum(float(r["预约Epsilon"]) for r in reservations))
        quota = float(period["额度Epsilon"])
        settled_balance = _r(quota - used - reserved)  # 未被费用/预约占用的剩余额度，不结转

        settlement_no = f"STL-{code}"
        settlement = {
            "id": self._next_id(self.SETTLEMENT),
            "status": "已生成",
            "pending": True,
            "abnormal": False,
            "结算单编号": settlement_no,
            "账期编号": code,
            "关联预算": period.get("关联预算", ""),
            "额度Epsilon": _r(quota),
            "已执行费用": used,
            "未清预约占用": reserved,
            "结转预约Epsilon": reserved,
            "结算余额": settled_balance,
            "关账后退款累计": 0.0,
            "关账后净额": _r(settled_balance),
            "已领取Epsilon": 0.0,
            "结转剩余": reserved,
            "关账时间": "2026-11-26 00:00",
            "费用明细": [c["费用编号"] for c in charges],
            "预约明细": [r["预约编号"] for r in reservations],
        }
        self._rows(self.SETTLEMENT).append(settlement)

        # 账期本身冻结：已用/占用快照保留（已执行费用留在原周期），可用余额清零。
        period["status"] = "已关闭"
        period["pending"] = False
        period["可用Epsilon"] = 0.0
        period["结算单编号"] = settlement_no

        # 仍可执行的旧预约：额度来源改挂到结算单结转额度，保证来源明确。
        for reservation in reservations:
            reservation["status"] = "可领取"
            reservation["结算单编号"] = settlement_no
            reservation["额度来源"] = f"结算单{settlement_no}结转额度"

        return settlement, (
            f"账期 {code} 已关闭：已执行费用 {used}、未清预约结转 {reserved}、"
            f"结算余额 {settled_balance} 不结转，结算单 {settlement_no} 已生成"
        )

    # ————————————————————————————————————
    # 2. 待退款处理：幂等回执 + 退款归期
    # ————————————————————————————————————
    def apply_refund(
        self,
        *,
        receipt_no: str,
        charge_no: str,
        amount: float,
        arrival_period: str = "",
    ) -> tuple[dict[str, Any] | None, str]:
        receipt_no = receipt_no.strip()
        charge_no = charge_no.strip()
        amount = _r(amount)
        if not receipt_no or not charge_no:
            return None, "回执编号和费用编号不能为空"
        if amount <= 0:
            return None, "退款 Epsilon 必须大于 0"

        # 幂等：同一回执编号无论重放多少次，只受理一次，绝不重复增加余额。
        existing = self._find_by(self.REFUND, "回执编号", receipt_no)
        if existing is not None:
            return existing, (
                f"回执 {receipt_no} 已受理，重复回执不再入账；"
                f"该笔额度已归属账期 {existing['入账账期']}（来源账期 {existing['来源账期']}）"
            )

        charge = self._find_by(self.CHARGE, "费用编号", charge_no)
        if charge is None:
            return None, f"费用 {charge_no} 不存在，无法退款"

        refunded = float(charge.get("已退Epsilon", 0.0))
        if _r(refunded + amount) > float(charge["Epsilon金额"]):
            return None, (
                f"退款超额：费用 {charge_no} 金额 {charge['Epsilon金额']}，"
                f"已退 {refunded}，本次 {amount} 超过可退上限"
            )

        source_code = charge["账期编号"]
        source_period = self._period_by_code(source_code)
        settlement_no = source_period.get("结算单编号", "") if source_period else ""
        source_closed = bool(source_period and source_period["status"] == "已关闭")

        if source_closed:
            # 关账后到达的退款：跟随费用原账期，计入结算单的关账后退款，
            # 不进入退款到达窗口（新账期）的余额。
            target_code = source_code
            refund_type = "关账后退款"
            settlement = self._find_by(self.SETTLEMENT, "结算单编号", settlement_no)
            if settlement is not None:
                settlement["关账后退款累计"] = _r(
                    float(settlement["关账后退款累计"]) + amount)
                settlement["关账后净额"] = _r(
                    float(settlement["结算余额"]) + float(settlement["关账后退款累计"]))
            period = source_period
            period["关账后退款累计"] = _r(float(period.get("关账后退款累计", 0.0)) + amount)
            message = (
                f"退款 {amount} 跟随费用原账期 {source_code} 计入结算单 {settlement_no} "
                f"关账后退款，未增加到达账期 {arrival_period or '（未指定）'} 的余额"
            )
        else:
            # 开放账期退款：退回原账期可用余额。
            target_code = source_code
            refund_type = "账期内退款"
            period = source_period
            period["可用Epsilon"] = _r(float(period["可用Epsilon"]) + amount)
            message = f"退款 {amount} 已退回开放账期 {source_code} 的可用余额"

        charge["已退Epsilon"] = _r(refunded + amount)
        charge["status"] = (
            "已退款" if _r(float(charge["已退Epsilon"])) >= float(charge["Epsilon金额"])
            else "部分退款"
        )

        refund = {
            "id": self._next_id(self.REFUND),
            "status": "已受理",
            "pending": False,
            "abnormal": False,
            "回执编号": receipt_no,
            "费用编号": charge_no,
            "退款Epsilon": amount,
            "来源账期": source_code,
            "入账账期": target_code,
            "结算单编号": settlement_no,
            "退款类型": refund_type,
            "到达窗口": arrival_period,
            "到达时间": "2026-11-26 00:00",
        }
        self._rows(self.REFUND).append(refund)
        return refund, message

    def trace_receipt(self, receipt_no: str) -> dict[str, Any] | None:
        """回执追查：这笔额度到底进入哪个账期、关联哪张结算单。"""
        refund = self._find_by(self.REFUND, "回执编号", receipt_no.strip())
        if refund is None:
            return None
        target = self._period_by_code(refund["入账账期"])
        return {
            "refund": refund,
            "入账账期状态": target["status"] if target else "账期不存在",
            "说明": (
                "退款跟随费用原账期归期，未在其他账期重复增加余额"
                if refund["退款类型"] == "关账后退款"
                else "退款已退回原开放账期可用余额"
            ),
        }

    # ————————————————————————————————————
    # 3. 旧预约领取配置：噪声引擎据此判断还能否领取
    # ————————————————————————————————————
    def reservation_eligibility(self, reservation_id: int) -> dict[str, Any]:
        reservation = self._find(self.RESERVATION, reservation_id)
        if reservation is None:
            return {"reservation_id": reservation_id, "eligible": False,
                    "reason": "预约不存在或已归档"}
        if reservation["status"] == "已领取":
            return {"reservation_id": reservation_id, "eligible": False,
                    "reason": "预约已领取过配置，不能重复占用额度",
                    "reservation": reservation}
        if reservation["status"] == "已失效":
            return {"reservation_id": reservation_id, "eligible": False,
                    "reason": "预约已失效", "reservation": reservation}

        need = float(reservation["预约Epsilon"])
        code = reservation["账期编号"]
        period = self._period_by_code(code)
        if period is None:
            return {"reservation_id": reservation_id, "eligible": False,
                    "reason": f"来源账期 {code} 不存在", "reservation": reservation}

        if period["status"] != "已关闭":
            available = float(period["可用Epsilon"])
            if available + 1e-9 < need:
                return {"reservation_id": reservation_id, "eligible": False,
                        "reason": f"开放账期 {code} 可用余额 {available} 不足 {need}",
                        "额度来源": reservation["额度来源"], "reservation": reservation}
            return {"reservation_id": reservation_id, "eligible": True,
                    "reason": "开放账期可用余额充足",
                    "额度来源": reservation["额度来源"],
                    "可用余额": _r(available), "reservation": reservation}

        settlement_no = reservation.get("结算单编号") or period.get("结算单编号", "")
        settlement = self._find_by(self.SETTLEMENT, "结算单编号", settlement_no)
        if settlement is None:
            return {"reservation_id": reservation_id, "eligible": False,
                    "reason": "账期已关闭但找不到结转结算单，额度来源不明",
                    "reservation": reservation}
        remaining = float(settlement["结转剩余"])
        if remaining + 1e-9 < need:
            return {"reservation_id": reservation_id, "eligible": False,
                    "reason": f"结算单 {settlement_no} 结转剩余 {remaining} 不足 {need}",
                    "额度来源": reservation["额度来源"], "reservation": reservation}
        return {"reservation_id": reservation_id, "eligible": True,
                "reason": "结算单结转额度充足，旧预约可继续领取配置",
                "额度来源": reservation["额度来源"],
                "结算单编号": settlement_no,
                "结转剩余": _r(remaining), "reservation": reservation}

    def claim_reservation(self, reservation_id: int) -> tuple[dict[str, Any] | None, str]:
        check = self.reservation_eligibility(reservation_id)
        if not check.get("eligible"):
            return None, check.get("reason", "预约不满足领取条件")
        reservation = check["reservation"]
        need = float(reservation["预约Epsilon"])
        period = self._period_by_code(reservation["账期编号"])

        if period["status"] != "已关闭":
            period["可用Epsilon"] = _r(float(period["可用Epsilon"]) - need)
            period["占用Epsilon"] = _r(max(0.0, float(period["占用Epsilon"]) - need))
        else:
            settlement = self._find_by(
                self.SETTLEMENT, "结算单编号", reservation["结算单编号"])
            settlement["已领取Epsilon"] = _r(
                float(settlement["已领取Epsilon"]) + need)
            settlement["结转剩余"] = _r(
                float(settlement["结转剩余"]) - need)
            if float(settlement["结转剩余"]) <= 1e-9:
                settlement["status"] = "已清零"
                settlement["pending"] = False
            else:
                settlement["status"] = "已结转"

        reservation["status"] = "已领取"
        reservation["pending"] = False
        reservation["领取时间"] = "2026-11-26 00:00"
        return reservation, (
            f"预约 {reservation['预约编号']} 已领取噪声配置 "
            f"{reservation['关联噪声配置']}，额度来源：{reservation['额度来源']}"
        )


budget_cycle_service = BudgetCycleService()
