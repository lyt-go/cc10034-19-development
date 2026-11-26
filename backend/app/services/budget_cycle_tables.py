"""周期结算配套资源服务：账期、费用、预约、结算单、退款回执沿用通用 CRUD 骨架。

真正的状态流转（关账、退款、领取配置）集中在 budget_cycle.BudgetCycleService，
这里只声明字段、状态和动作范围，让通用资源路由 /api/{module} 能直接服务这些表。
"""
from __future__ import annotations

from app.services.base import BaseModuleService


class BudgetPeriodService(BaseModuleService):
    MODULE = "budget_period"
    ENTITY = "预算账期"
    OPERATION_TERM = "查询"
    LIST_FIELDS = [
        "账期编号", "周期名称", "关联预算", "额度Epsilon", "已用Epsilon",
        "占用Epsilon", "可用Epsilon", "开始日期", "结束日期",
        "结算单编号", "关账后退款累计",
    ]
    REQUIRED_FIELDS = ["账期编号", "关联预算", "额度Epsilon"]
    STATUS_ORDER = ["开放", "待关闭", "已关闭"]
    ACTION_RULES = {"提交关闭": "待关闭"}
    NEGATIVE_ACTIONS = []


class BudgetChargeService(BaseModuleService):
    MODULE = "budget_charge"
    ENTITY = "已执行费用"
    OPERATION_TERM = "查询"
    LIST_FIELDS = [
        "费用编号", "账期编号", "来源查询", "Epsilon金额", "已退Epsilon", "入账时间",
    ]
    REQUIRED_FIELDS = ["费用编号", "账期编号", "Epsilon金额"]
    STATUS_ORDER = ["已入账", "部分退款", "已退款"]
    ACTION_RULES: dict[str, str] = {}
    NEGATIVE_ACTIONS = []


class BudgetReservationService(BaseModuleService):
    MODULE = "budget_reservation"
    ENTITY = "未清预约"
    OPERATION_TERM = "查询"
    LIST_FIELDS = [
        "预约编号", "账期编号", "关联噪声配置", "预约Epsilon",
        "额度来源", "结算单编号", "创建时间", "领取时间",
    ]
    REQUIRED_FIELDS = ["预约编号", "账期编号", "预约Epsilon"]
    STATUS_ORDER = ["待领取", "可领取", "已领取", "已失效"]
    ACTION_RULES: dict[str, str] = {}
    NEGATIVE_ACTIONS = []


class BudgetSettlementService(BaseModuleService):
    MODULE = "budget_settlement"
    ENTITY = "预算结算单"
    OPERATION_TERM = "查询"
    LIST_FIELDS = [
        "结算单编号", "账期编号", "额度Epsilon", "已执行费用", "未清预约占用",
        "结转预约Epsilon", "结算余额", "关账后退款累计", "关账后净额",
        "已领取Epsilon", "结转剩余", "关账时间",
    ]
    REQUIRED_FIELDS = ["结算单编号", "账期编号"]
    STATUS_ORDER = ["已生成", "已结转", "已清零"]
    ACTION_RULES: dict[str, str] = {}
    NEGATIVE_ACTIONS = []


class BudgetRefundService(BaseModuleService):
    MODULE = "budget_refund"
    ENTITY = "退款回执"
    OPERATION_TERM = "查询"
    LIST_FIELDS = [
        "回执编号", "费用编号", "退款Epsilon", "来源账期", "入账账期",
        "结算单编号", "退款类型", "到达时间",
    ]
    REQUIRED_FIELDS = ["回执编号", "费用编号", "退款Epsilon"]
    STATUS_ORDER = ["已受理", "重复回执"]
    ACTION_RULES: dict[str, str] = {}
    NEGATIVE_ACTIONS = []
