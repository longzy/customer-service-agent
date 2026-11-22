import type { components } from "@/lib/api-types";

// 消息契约来自 FastAPI OpenAPI 生成类型；不要手写响应字段。
export type Message = components["schemas"]["MessagePublic"];
export type MessagePage = components["schemas"]["MessagePageResponse"];
export type MessageAuthor = Message["author_type"];
export type OrderSummary = components["schemas"]["OrderSummaryPublic"];
export type CancellationSummary = components["schemas"]["CancellationSummary"];
