type ErrorBody = {
  code?: unknown;
  message?: unknown;
  detail?: unknown;
};

const FALLBACK_ERROR = "请求失败，请稍后再试";

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export async function readError(response: Response): Promise<ApiError> {
  let body: ErrorBody = {};
  try {
    body = (await response.json()) as ErrorBody;
  } catch {
    // 非 JSON 响应沿用兜底文案。
  }
  // 契约：优先 message，其次 detail；两者都兼容非字符串的兜底响应。
  const message =
    (typeof body.message === "string" && body.message.trim()) ||
    (typeof body.detail === "string" && body.detail.trim()) ||
    FALLBACK_ERROR;
  const code = typeof body.code === "string" ? body.code : undefined;
  return new ApiError(message, response.status, code);
}
