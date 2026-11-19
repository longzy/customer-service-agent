# ADR-0009：请求级 Unit of Work

- 状态：已批准
- 日期：2026-11-19
- 批准：2026-11-19（用户确认继续事务收口）
- 修订：2026-11-19（用户确认 `scope="function"` 修复 commit 失败响应语义）
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
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
```

规则：

1. 路由与业务模块只 `flush`，**不得调用 `commit()`**；请求成功由依赖统一提交，异常统一回滚。
2. 所有 `Depends(get_session)` 必须显式声明 `scope="function"`：依赖在响应发送前清理，`commit` 失败才能在响应发出前转成 500。禁止 request-scope（默认）与 function-scope 混用。
3. 独立事务必须新开 session，不复用请求 session：
   - 限速桶（`identity/rate_limit.py`）；
   - 安全事件审计（`audit/service.record_security`）；
   - Trace 工具执行记录（`AsyncTraceSink`）；
   - 启动恢复的取消工作流。
4. 独立事务在组件名或注释中显式标注，评审按此检查。
5. 只读请求同样经过 UoW；空事务的 `COMMIT` 开销接受，暂不做读写 session 分离。

## 后果

- 「漏 commit」在结构上不可能发生；新增路由不需要复制提交代码。
- 请求内所有业务写延迟到响应结束时提交，事务原子性由请求边界保证。
- `scope="function"` 使依赖在响应发送前清理；`commit` 失败会抛到全局异常处理器并返回 500 封套，客户端不会先收到 200。若 `commit` 已发出但连接在确认前断开，结果仍是不确定的，客户端重试依赖接口幂等键。
- 依赖树必须统一 function scope：request-scope 依赖不能依赖 function-scope 依赖，FastAPI 会直接报错；并列的 `Depends(get_session)` 也必须全部改，否则会各自创建 session。
- 只读请求同样提交空事务；空事务失败也返回 500。
- 模型调用期间事务保持打开（客户消息 10s 超时），连接占用时间不变，但连接池参数仍需单独治理。
- 测试通过真实 API 查库即可验证提交；审计 503 用例继续验证回滚；新增 commit 失败用例验证 500 与回滚。

## 拒绝的方案

- **每个路由手动 commit**：现状，无法防止遗漏与跨层提交。
- **request-scope 依赖（FastAPI 默认）**：清理在响应发送后，`commit` 失败无法改写已发出的 200；这是本次修订前的行为。
- **handler 事务装饰器**：可以做到发送前提交，但需要逐路由添加、从 `kwargs` 取 session、处理与 `get_session` 的重复 commit，新增路由容易漏；function scope 是框架原生、声明式且不会漏。
- **中间件管理事务**：需要把 session 放进 `request.state` 或 `ContextVar`，与 FastAPI 依赖注入重复；function scope 已能在不引入中间件的前提下解决 teardown 时机。
- **SQLAlchemy autocommit**：2.0 已移除该模式，且语义更隐式。
- **读写 session 分离**：当前读接口也会刷新 `last_seen_at`，拆分需要先改认证依赖，收益不足以在本切片引入。

## 修订记录

- 2026-11-19：`get_session` 改为在 `try` 内 `commit`（失败也回滚）；所有注入点改为 `Depends(get_session, scope="function")`；FastAPI 下限提升到 `0.121.1`。commit 失败现在返回 500。
