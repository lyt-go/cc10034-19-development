"""周期结算领域测试：关账、退款归期、旧预约领取配置、回执幂等。

运行：cd backend && python3 -m pytest tests/test_budget_cycle.py -v
"""
from __future__ import annotations

import pytest

from app.services.budget_cycle import budget_cycle_service as svc
from app.services.noise_engine import NoiseEngineService
from app.store import store


@pytest.fixture(autouse=True)
def fresh_store():
    """每个用例基于种子数据重新构造内存仓库，避免用例间相互污染。"""
    store.__init__()
    yield


def _period(code: str):
    return next(r for r in store.rows("budget_period") if r["账期编号"] == code)


def _settlement(code: str):
    return next(
        (r for r in store.rows("budget_settlement") if r["账期编号"] == code), None)


def _refund(receipt_no: str):
    return next(
        (r for r in store.rows("budget_refund") if r["回执编号"] == receipt_no), None)


class TestPeriodClose:
    def test_seed_period_matches_scenario(self):
        """种子账期即需求场景：额度 1.0、已用 0.4、占用 0.2、可用 0.4。"""
        period = _period("P-202610")
        assert float(period["额度Epsilon"]) == 1.0
        assert float(period["已用Epsilon"]) == 0.4
        assert float(period["占用Epsilon"]) == 0.2
        assert float(period["可用Epsilon"]) == 0.4

    def test_close_generates_settlement_from_charges_and_reservations(self):
        settlement, message = svc.submit_close(1)
        assert settlement is not None, message
        # 已执行费用 0.25 + 0.15 = 0.4，未清预约占用 0.2
        assert float(settlement["已执行费用"]) == 0.4
        assert float(settlement["未清预约占用"]) == 0.2
        assert float(settlement["结转预约Epsilon"]) == 0.2
        # 结算余额 = 1.0 - 0.4 - 0.2 = 0.4，不结转
        assert float(settlement["结算余额"]) == 0.4
        assert float(settlement["结转剩余"]) == 0.2

    def test_close_freezes_period_and_keeps_used_fee_in_origin(self):
        svc.submit_close(1)
        period = _period("P-202610")
        assert period["status"] == "已关闭"
        assert float(period["可用Epsilon"]) == 0.0
        # 已完成费用保留在原周期：费用行的账期编号不变、已用快照不变
        assert float(period["已用Epsilon"]) == 0.4
        charges = [c for c in store.rows("budget_charge") if c["账期编号"] == "P-202610"]
        assert len(charges) == 2
        assert sum(float(c["Epsilon金额"]) for c in charges) == 0.4

    def test_close_marks_old_reservation_with_explicit_quota_source(self):
        svc.submit_close(1)
        reservation = store.find("budget_reservation", 1)
        assert reservation["status"] == "可领取"
        assert reservation["结算单编号"] == "STL-P-202610"
        assert "STL-P-202610" in reservation["额度来源"]

    def test_close_is_idempotent_guard(self):
        svc.submit_close(1)
        again, message = svc.submit_close(1)
        assert again is None
        assert "已关闭" in message
        assert len(store.rows("budget_settlement")) == 1

    def test_close_unknown_period(self):
        result, message = svc.submit_close(999)
        assert result is None
        assert "不存在" in message


class TestRefundAttribution:
    def test_refund_after_close_enters_origin_period_not_arrival_window(self):
        svc.submit_close(1)
        old_period = _period("P-202610")
        new_period = _period("P-202611")
        new_available_before = float(new_period["可用Epsilon"])

        # 退款在另一窗口（11 月账期）到达，但费用属于 10 月账期
        refund, message = svc.apply_refund(
            receipt_no="RCP-0001", charge_no="CHG-0001",
            amount=0.25, arrival_period="P-202611")
        assert refund is not None, message
        assert refund["来源账期"] == "P-202610"
        assert refund["入账账期"] == "P-202610"
        assert refund["退款类型"] == "关账后退款"

        # 新账期余额分毫不增加
        assert float(new_period["可用Epsilon"]) == new_available_before == 1.0
        # 旧账期结算单记录关账后退款，净额 = 结算余额 0.4 + 退款 0.25
        settlement = _settlement("P-202610")
        assert float(settlement["关账后退款累计"]) == 0.25
        assert float(settlement["关账后净额"]) == 0.65
        assert float(old_period["关账后退款累计"]) == 0.25

    def test_duplicate_receipt_never_double_counts(self):
        svc.submit_close(1)
        first, msg1 = svc.apply_refund(
            receipt_no="RCP-0001", charge_no="CHG-0001", amount=0.25,
            arrival_period="P-202611")
        assert first is not None
        # 同回执重放，哪怕金额/窗口不同也必须幂等
        second, msg2 = svc.apply_refund(
            receipt_no="RCP-0001", charge_no="CHG-0001", amount=0.25,
            arrival_period="P-202611")
        assert second["id"] == first["id"]
        assert "重复回执" in msg2
        assert len(store.rows("budget_refund")) == 1
        settlement = _settlement("P-202610")
        assert float(settlement["关账后退款累计"]) == 0.25
        charge = next(c for c in store.rows("budget_charge") if c["费用编号"] == "CHG-0001")
        assert float(charge["已退Epsilon"]) == 0.25

    def test_trace_receipt_locates_target_period(self):
        svc.submit_close(1)
        svc.apply_refund(
            receipt_no="RCP-0002", charge_no="CHG-0002", amount=0.15,
            arrival_period="P-202611")
        trace = svc.trace_receipt("RCP-0002")
        assert trace is not None
        assert trace["refund"]["入账账期"] == "P-202610"
        assert trace["入账账期状态"] == "已关闭"
        assert svc.trace_receipt("NOT-EXIST") is None

    def test_refund_cannot_exceed_charge_amount(self):
        svc.submit_close(1)
        result, message = svc.apply_refund(
            receipt_no="RCP-X", charge_no="CHG-0001", amount=0.9)
        assert result is None
        assert "超额" in message
        assert _refund("RCP-X") is None

    def test_partial_then_full_refund_updates_charge_status(self):
        svc.submit_close(1)
        svc.apply_refund(receipt_no="RCP-A", charge_no="CHG-0001",
                         amount=0.1, arrival_period="P-202611")
        charge = next(c for c in store.rows("budget_charge") if c["费用编号"] == "CHG-0001")
        assert charge["status"] == "部分退款"
        svc.apply_refund(receipt_no="RCP-B", charge_no="CHG-0001",
                         amount=0.15, arrival_period="P-202611")
        assert charge["status"] == "已退款"
        assert float(charge["已退Epsilon"]) == 0.25

    def test_refund_on_open_period_returns_to_available_balance(self):
        # 11 月账期处于开放状态，登记一笔费用再退，余额应回到该账期
        period = _period("P-202611")
        store.rows("budget_charge").append({
            "id": 3, "status": "已入账", "pending": True, "abnormal": False,
            "费用编号": "CHG-0003", "账期编号": "P-202611", "来源查询": "DIFF-0009",
            "Epsilon金额": 0.3, "已退Epsilon": 0.0, "入账时间": "2026-11-05 11:00",
        })
        period["已用Epsilon"] = 0.3
        period["可用Epsilon"] = 0.7
        refund, message = svc.apply_refund(
            receipt_no="RCP-OPEN", charge_no="CHG-0003", amount=0.3)
        assert refund is not None, message
        assert refund["退款类型"] == "账期内退款"
        assert float(period["可用Epsilon"]) == 1.0


class TestOldReservationClaim:
    def test_noise_engine_gate_uses_settlement_after_close(self):
        svc.submit_close(1)
        gate = NoiseEngineService().check_reservation(1)
        assert gate["eligible"] is True
        assert gate["gate"] == "noise_engine"
        assert gate["结算单编号"] == "STL-P-202610"
        assert float(gate["结转剩余"]) == 0.2

    def test_claim_deducts_settlement_carry_forward(self):
        svc.submit_close(1)
        reservation, message = svc.claim_reservation(1)
        assert reservation is not None, message
        assert reservation["status"] == "已领取"
        settlement = _settlement("P-202610")
        assert float(settlement["已领取Epsilon"]) == 0.2
        assert float(settlement["结转剩余"]) == 0.0
        assert settlement["status"] == "已清零"

    def test_claim_before_close_uses_open_period_balance(self):
        # 不关账直接领取：扣开放账期可用余额与占用
        reservation, message = svc.claim_reservation(1)
        assert reservation is not None, message
        period = _period("P-202610")
        assert float(period["可用Epsilon"]) == 0.2  # 0.4 - 0.2
        assert float(period["占用Epsilon"]) == 0.0

    def test_claim_is_single_use(self):
        svc.submit_close(1)
        svc.claim_reservation(1)
        again, message = svc.claim_reservation(1)
        assert again is None
        assert "重复" in message

    def test_claim_blocked_when_carry_forward_exhausted(self):
        svc.submit_close(1)
        # 人为把结转剩余调到 0，模拟额度已被其他预约领完
        settlement = _settlement("P-202610")
        settlement["结转剩余"] = 0.0
        result, message = svc.claim_reservation(1)
        assert result is None
        assert "不足" in message

    def test_full_scenario_two_period_balances(self):
        """端到端：关账 → 退款跨窗口到达 → 两期余额核对 → 旧预约领取。"""
        svc.submit_close(1)
        svc.apply_refund(
            receipt_no="RCP-E2E", charge_no="CHG-0001", amount=0.25,
            arrival_period="P-202611")

        old_period = _period("P-202610")
        new_period = _period("P-202611")
        # 旧账期：余额冻结为 0，费用 0.4 保留，退款只体现在结算单
        assert float(old_period["可用Epsilon"]) == 0.0
        assert float(old_period["已用Epsilon"]) == 0.4
        # 新账期：退款未进入，余额保持初始 1.0
        assert float(new_period["可用Epsilon"]) == 1.0

        # 旧预约仍可凭结算单结转额度领取配置
        gate = NoiseEngineService().check_reservation(1)
        assert gate["eligible"] is True
        reservation, _ = svc.claim_reservation(1)
        assert reservation["额度来源"] == "结算单STL-P-202610结转额度"

        settlement = _settlement("P-202610")
        # 关账后净额只受退款影响，不受领取影响；领取消耗的是结转额度
        assert float(settlement["关账后净额"]) == 0.65
        assert float(settlement["结转剩余"]) == 0.0
