# ADR-0009：请求级 Unit of Work

- 状态：已批准
- 日期：2026-11-19
- 批准：2026-11-19（用户确认继续事务收口）
- 关联：[总体架构](../architecture/overview.md) 第 5 节、[ADR-0008](0008-business-domain-http-layout.md)

## 背景

`get_session` 原先只借出 `AsyncSession`，不提交也不回滚。请求正常结束时 `close()` 静默回滚，是否落库完全取决于每个路由是否记得写 `await db.commit()`。

由此产生四类问题：

- 漏写 `commit` 的路由返回 200，数据消失，没有异常与日志；
- 同一 `AsyncSession` 被 API、service、workflow、限速共享，任何一处 `commit` 都会提交其他层挂起的写入；
- 一个请求出现 2 到 4 个提交点，失败时留下半提交；
- 新路由要靠复制旧路由的 `commit` 来保证正确性。

M1 收口时后端共有 36 处 `commit()` 调用，分布在 10 个文件。

## 决策

`get_session` 升级为请求级 Unit of Work：

```python
async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise
        else:
            await session.commit()
```

规则：

1. 路由与业务模块只 `flush`，**不得调用 `commit()`**；请求成功由依赖统一提交，异常统一回滚。
2. 独立事务必须新开 session，不复用请求 session：
   - 限速桶（`identity/rate_limit.py`）；
   - 安全事件审计（`audit/service.record_security`）；
   - Trace 工具执行记录（`AsyncTraceSink`）；
   - 启动恢复的取消工作流。
3. 独立事务在组件名或注释中显式标注，评审按此检查。
4. 只读请求同样经过 UoW；空事务的 `COMMIT` 开销接受，暂不做读写 session 分离。

## 后果

- 「漏 commit」在结构上不可能发生；新增路由不需要复制提交代码。
- 请求内所有业务写延迟到响应结束时提交，事务原子性由请求边界保证。
- FastAPI 的 yield 依赖在响应发送后执行 teardown；`commit` 失败时客户端可能已收到 200。数据会回滚，客户端重试依赖接口幂等键；服务端记录异常日志。
- 模型调用期间事务保持打开（客户消息 10s 超时），连接占用时间不变，但连接池参数仍需单独治理。
- 测试通过真实 API 查库即可验证提交；审计 503 用例继续验证回滚。

## 拒绝的方案

- **每个路由手动 commit**：现状，无法防止遗漏与跨层提交。
- **中间件管理事务**：需要把 session 放进 `request.state` 或 `ContextVar`，与 FastAPI 依赖注入重复；teardown 时机问题相同。
- **SQLAlchemy autocommit**：2.0 已移除该模式，且语义更隐式。
- **读写 session 分离**：当前读接口也会刷新 `last_seen_at`，拆分需要先改认证依赖，收益不足以在本切片引入。
