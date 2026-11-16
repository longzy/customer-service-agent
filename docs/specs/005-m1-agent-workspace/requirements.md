# 005 坐席工作台实现规格

- 状态：草案
- 日期：2026-11-16
- 级别：T3（员工认证/RBAC、队列归属、审计）
- 依据：[003 M1 验收与契约](../003-m1-customer-service-loop/design.md)、[003 requirements](../003-m1-customer-service-loop/requirements.md)
- AC：**本 spec 不新增 AC**；验收引用 003 的 AC-37、38、39、40、41、43、45、46、47，以及 AC-48 坐席路径
- 范围：员工登录/session/RBAC、队列、领取、接管、工作台上下文、回复、关闭/转回、审计、工作台前端
- 不范围：客户匿名会话/AI/订单校验（004）、取消 actor/确认（006）
- 下一步：S1 写实现范围与 FR（引用 003 AC），S2 设计，S3 任务地图。
