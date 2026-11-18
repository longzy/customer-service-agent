import { readError } from "@/lib/api-client";
import type { components } from "@/lib/api-types";

import type { MessagePage } from "../types";

type CustomerMessageRequest = components["schemas"]["CustomerMessageRequest"];

export async function getMessages(afterId: number): Promise<MessagePage> {
  const response = await fetch(`/api/customer/messages?after_id=${encodeURIComponent(afterId)}`);
  if (!response.ok) {
    throw await readError(response);
  }
  return (await response.json()) as MessagePage;
}

export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `idem-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export async function sendMessage(
  content: string,
  idempotencyKey: string = newIdempotencyKey(),
): Promise<MessagePage> {
  const body: CustomerMessageRequest = { content };
  const response = await fetch("/api/customer/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw await readError(response);
  }
  return (await response.json()) as MessagePage;
}
