# ADR-0008：后端 HTTP 入口按业务域组织

- 状态：已批准
- 日期：2026-11-19
- 批准：2026-11-19（用户确认按业务域组织）
- 关联：[总体架构](../architecture/overview.md) 第 9 节、[ADR-0004 工程基线](0004-engineering-baseline.md)
- 取代：ADR-0004 的 `backend/api` 目录划分（仅目录部分；技术栈与检查规范继续有效）

## 背景

M1 的客户与工作台路由集中在两个文件：

- `backend/api/customer_routes.py`：客户登录、会话、消息、关闭、登出；
- `backend/api/workspace_routes.py`：员工登录、队列、领取、接管、回复、关闭、转回。

由此产生三个问题：

1. 一个用例跨 `api`、`conversations`、`identity`、`audit` 四个目录，改一处要读五六个文件；
2. 身份路由与业务路由混在同一文件，`identity` 域没有 HTTP 入口；
3. DTO 在 `api` 下按端拆分，域内看不到自己的契约。

Java 式的全局 `controller/service/repository/dao/dto/mapper` 分层不能解决这些问题，反而会在 Python 中制造空壳接口与 Mapper 层。

## 决策

按**业务域**放 HTTP 入口，域内自带路由、DTO 与认证依赖：

```text
backend/
  api/                     # 应用装配、中间件、共享 HTTP 错误与审计编排
    main.py
    csrf.py
    request_id.py
    errors.py
    service_audit.py
    audit.py               # 旧取消工作流审计（保留）
    admin_routes.py        # 仅开发/测试的 Mock OMS 故障注入
  platform/                # 配置、数据库、trace、共享 HTTP 工具与错误封套
    http.py
    schemas.py
  identity/                # 身份域
    http.py                # 员工登录、会话恢复、登出
    customer_auth.py       # 客户认证依赖（供会话域使用）
    employee_auth.py       # 员工认证依赖
    schemas.py             # 员工登录与会话 DTO
    cookies.py             # 客户/员工 session Cookie
  conversations/           # 会话域
    customer_http.py       # 客户登录、会话、消息、关闭、登出
    workspace_http.py      # 队列、领取、接管、回复、关闭、转回
    schemas.py             # 客户与工作台 DTO
  audit/                   # 审计写入
  domain/                  # 纯业务规则
  agent_runtime/           # 模型调用与意图
  tools/                   # Tool 网关
  workflows/               # 取消工作流
  adapters/oms/            # OMS 端口与适配器
```

约束：

- 新增业务路由放进对应域的 `*_http.py`，不回到 `api/`。
- 域的 DTO 放进域的 `schemas.py`；跨域共享的 HTTP 类型放 `platform/schemas.py`。
- `api/` 只做应用装配、中间件、异常映射与审计编排，不承载业务规则。
- 不引入 Service 接口 + Impl、全局 Repository 接口或独立 Mapper 层；持久化直接用 `AsyncSession`。
- `Identity` 值对象仍由 `identity/__init__.py` 提供，供旧取消工作流使用。

## 后果

- OpenAPI 契约不变：15 条路径与组件集合保持一致，前端生成类型无需修改。
- 路由文件按域拆分，新增用例的改动范围落在一个域目录。
- `api/errors.py` 与 `api/service_audit.py` 仍是域 HTTP 入口的共享依赖，这是当前折衷；后续可抽到独立 HTTP 内核。
- 事务边界问题（`commit` 散落在路由与 workflow）不在本 ADR 解决，由 Unit of Work 改造单独处理。

## 拒绝的方案

- **一次性迁到 `backend/modules/<domain>/`**：收益不足以抵消 import、测试与脚本迁移成本；M1 的域数量少，现有顶层名已足够表达边界。
- **Java 式全局五层**：Python 缺少编译期接口约束，接口 + Impl 与 Mapper 层多为样板代码。
- **为每张表建 Repository 接口**：SQLAlchemy `AsyncSession` 已提供持久化抽象，项目也没有替换存储的需求。
