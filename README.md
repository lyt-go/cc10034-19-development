# 数据安全计算与隐私保护平台

面向数据脱敏、差分隐私、安全聚合与访问审计的数据安全计算与隐私保护平台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/WorkbenchView.vue|tsx  全部模块共享工作台
│   ├── src/views/BudgetCycleView.vue    周期结算页（关账/退款/旧预约领取）
│   ├── src/data/modules.ts              18个业务模块配置
│   ├── src/api/              统一请求封装
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/resource.py  通用查询/导出/登记/动作接口
│   ├── app/routers/budget_cycle.py  周期结算专用接口（关账/退款/追查/领取）
│   ├── app/services/<key>.py    每个模块独立领域逻辑
│   ├── app/services/budget_cycle.py  账期关闭与退款归期的状态流转门面
│   ├── app/services/base.py     共享服务骨架
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm ci
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 脱敏规则 | `mask_rule` | 脱敏规则 | 规则编号、目标字段、脱敏算法 |
| 隐私预算 | `privacy_budget` | 隐私预算 | 预算编号、数据集名称、总预算Epsilon |
| 噪声引擎 | `noise_engine` | 噪声配置 | 配置编号、噪声机制、Epsilon值 |
| 安全聚合 | `secure_agg` | 聚合任务 | 任务编号、数据源列表、聚合函数 |
| 访问审计 | `access_audit` | 审计记录 | 记录编号、访问主体、目标资源 |
| 授权审批 | `grant_approval` | 授权申请 | 申请编号、申请人、目标数据 |
| 分级分类 | `classify_tag` | 分级标签 | 标签编号、数据资源、安全等级 |
| 联邦训练 | `federated_train` | 训练任务 | 任务编号、参与节点、模型类型 |
| 梯度加密 | `gradient_encrypt` | 加密配置 | 配置编号、加密方案、密钥长度 |
| 假名化 | `pseudonym` | 假名映射 | 映射编号、原始标识、假名标识 |
| K匿名检查 | `k_anonymity` | 匿名检查 | 检查编号、数据集名称、准标识符列 |
| 差分查询 | `differential_sql` | 查询记录 | 查询编号、查询语句、查询用户 |
| 密文索引 | `encrypt_index` | 索引条目 | 条目编号、加密域、索引类型 |
| 数据水印 | `watermark` | 水印记录 | 水印编号、目标数据集、水印算法 |
| 同意登记 | `consent_registry` | 同意记录 | 记录编号、数据主体、处理目的 |
| 风险扫描 | `risk_scan` | 扫描任务 | 任务编号、扫描范围、扫描规则 |
| 策略下发 | `deploy_policy` | 策略分发 | 分发编号、策略内容、目标节点 |
| 异常检测 | `anomaly_detect` | 异常规则 | 规则编号、检测维度、检测算法 |

### 周期结算（隐私预算扩展）

工作台新增「周期结算」入口（路由 `/budget_cycle`），后端模块总数由 18 增至 23，新增五张内存表与配套接口：

| 表 | key | 作用 |
| --- | --- | --- |
| 预算账期 | `budget_period` | 账期主表，维护额度/已用/占用/可用余额 |
| 已执行费用 | `budget_charge` | 账期内实际扣费，关账后仍保留在原周期，可退款 |
| 未清预约 | `budget_reservation` | 占用额度、待领取噪声配置的旧预约 |
| 预算结算单 | `budget_settlement` | 关账时按已执行费用+未清预约生成，记录结转与关账后退款 |
| 退款回执 | `budget_refund` | 按回执编号幂等，记录来源账期与实际入账账期 |

核心规则（实现见 `backend/app/services/budget_cycle.py`）：

- **关账**：`POST /api/budget-cycle/periods/{id}/close`，已执行费用保留原周期，未清预约结转到结算单并写明额度来源，未占用的结算余额不结转。
- **退款归期**：`POST /api/budget-cycle/refunds`，退款跟随费用原账期；原账期已关闭时计入该账期结算单的关账后退款，即使退款在新窗口到达也不增加新账期余额。
- **回执幂等**：同一回执编号重放只返回首条记录，任何账期都不会重复增加余额；`GET /api/budget-cycle/refunds/{no}/trace` 可追查额度去向。
- **旧预约领取**：噪声引擎经 `GET /api/budget-cycle/noise-engine/reservations/{id}/check` 判断资格——开放账期看可用余额，已关闭账期看结算单结转剩余；领取后来源额度立即扣减，重复领取被拒绝。

## 约定

- 全部模块共享`frontend/src/views/WorkbenchView.vue|tsx`和一套资源路由。
- 每个模块仍保留独立`backend/app/services/<模块>.py`；纯前端保留
  `frontend/src/domain/<模块>.ts`，用于承载真实业务差异并维持36题位容量。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

领域：数据工程
子方向：数据分析与数据应用
