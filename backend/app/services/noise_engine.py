"""噪声引擎领域服务：字段、状态和动作来自业务配置，数据处理骨架由基类复用。"""
from __future__ import annotations

from app.services.base import BaseModuleService


class NoiseEngineService(BaseModuleService):
    MODULE = "noise_engine"
    ENTITY = "噪声配置"
    OPERATION_TERM = "关联"
    LIST_FIELDS = ["配置编号", "噪声机制", "Epsilon值", "敏感度", "分布类型", "输出精度", "关联字段", "配置版本"]
    REQUIRED_FIELDS = ["配置编号", "噪声机制", "Epsilon值"]
    STATUS_ORDER = ["草稿", "待验证", "已生效", "已停用"]
    ACTION_RULES = {"提交验证": "待验证", "标记生效": "已生效", "停用配置": "已停用"}
    NEGATIVE_ACTIONS = ["停用配置"]

    def check_reservation(self, reservation_id: int) -> dict:
        """噪声引擎领取配置前的预算闸门：旧预约还能否领取，交给周期结算判断。

        延迟导入避免与 budget_cycle 模块在注册表初始化阶段产生循环依赖。
        """
        from app.services.budget_cycle import budget_cycle_service

        result = budget_cycle_service.reservation_eligibility(reservation_id)
        result["gate"] = "noise_engine"
        return result
