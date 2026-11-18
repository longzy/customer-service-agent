import type { components } from "@/lib/api-types";

// 会话入口契约来自 FastAPI OpenAPI 生成类型；不要手写响应字段。
export type ConversationDetail = components["schemas"]["WorkspaceConversationResponse"];
export type TakeoverResult = components["schemas"]["WorkspaceTakeoverResponse"];
