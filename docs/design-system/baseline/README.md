# 视觉验收基线（design freeze v1）

- 状态：已批准
- 冻结：2026-11-18（随 [ui-spec](../ui-spec.md) v4 与设计稿冻结）
- 用途：实现完成后与基线并排比对，判定「允许 / 需修 / 阻断」
- 图片来源：不复制图片，直接引用 [proposals/](../proposals/README.md) 的唯一副本；本目录只记录**冻结哈希**与比对流程

## 基线清单

图片是唯一副本，链接指向 `proposals/`；sha256 取前 12 位，用于判断“设计稿是否被改过”。

| 基线 | 页面 | 视口 | sha256 | 覆盖状态 |
|---|---|---|---|---|
| [customer-login](../proposals/2026-11-18-customer-login.png) | 客户登录 | 1440×960 | `fb398d172bd9` | 默认、聚焦、限速提示、测试账号提示 |
| [customer-chat](../proposals/2026-11-18-customer-chat.png) | 客户聊天 | 1440×960 | `289da03afb7c` | 消息、欢迎卡、转人工等待 |
| [agent-login](../proposals/2026-11-18-agent-login.png) | 坐席登录 | 1440×960 | `20519d524793` | 默认、聚焦、环境标识、审计 |
| [agent-console](../proposals/2026-11-18-agent-console.png) | 坐席队列 | 1440×960 | `372fd2fa67ae` | 选中行、超时行、详情、键盘条 |
| [agent-states](../proposals/2026-11-18-agent-states.png) | 队列四态 | 1440×676 | `f9797ba00c47` | 加载、空、错误、无权限 |
| [ui-components](../ui-components.png) | 组件参考页 | 1440×2050 | `b94656c8a0b3` | 令牌、基础组件、客户侧、坐席侧 |

## 截图流程

固定视口 1440×960（组件页 1440×2050）。macOS 上 Chrome headless 的 `innerHeight` 比 `--window-size` 少 144，因此**窗口高度要加 144**，截完裁掉底部 144：

```sh
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
"$CHROME" --headless=new --no-sandbox --disable-gpu \
  --hide-scrollbars --virtual-time-budget=2000 \
  --window-size=1440,1104 \
  --screenshot=/tmp/page.png "http://127.0.0.1:3000/login"
# 裁掉底部 144px 后与基线并排比对
```

- 客户侧服务：`pnpm -C apps/chat dev`；坐席侧：`pnpm -C apps/workspace dev`。
- 组件页基线直接截静态文件（`ui-components.html`），窗口 1440×2194。
- 需要自动化时，S2 引入 Playwright，用 `page.setViewportSize({ width: 1440, height: 960 })` 替代窗口补偿。

## 差异判定

| 类别 | 含义 | 处理 |
|---|---|---|
| 允许 | 字体抗锯齿、平台滚动条差异、1px 内取整 | 记录，不修 |
| 需修 | 间距、颜色、字号、圆角、阴影与基线不一致 | 修代码，不回改基线 |
| 阻断 | 布局错位、信息缺失、状态缺失、对比度不达标 | 不通过，修完重跑 |

## 变更流程

1. 先改 [ui-spec](../ui-spec.md) 或设计稿，写明原因与影响页面。
2. 重新导出 `proposals/` 的 PNG，**同步更新本页 sha256**（`shasum -a 256 <file>`）。
3. 再改代码。
4. 只改代码、或改了图不更新哈希，均视为违规；评审按「哈希、规范、代码」三者一致检查。

## 不覆盖

- 移动端与暗色模式：尚未设计，见 [ui-spec 2.8](../ui-spec.md) 的断点规则。
- 动效的逐帧还原：只验收入场、脉冲、spinner 的存在与时长，不做逐帧比对。
- 登录错误态、领取冲突提示等瞬态：由组件测试与手工走查覆盖，不进入截图基线。
