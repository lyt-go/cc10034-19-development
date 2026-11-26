"""业务路由汇总：跨模块链接与周期结算路由必须先于通用资源路由注册。"""
from __future__ import annotations

from app.routers import budget_cycle, cross_links, resource

ROUTERS = [budget_cycle, cross_links, resource]
