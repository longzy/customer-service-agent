export type Account = {
  account_id: string;
  display_name: string;
  tenant_id: string;
  tenant_name: string;
};

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string; message?: string };
    return body.detail ?? body.message ?? "请求失败";
  } catch {
    return "请求失败";
  }
}

export async function getAccounts(): Promise<Account[]> {
  const response = await fetch("/api/accounts");
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return (await response.json()) as Account[];
}

export async function getSession(): Promise<Account | null> {
  const response = await fetch("/api/session");
  if (response.status === 401) {
    return null;
  }
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return (await response.json()) as Account;
}

export async function login(accountId: string): Promise<Account> {
  const response = await fetch("/api/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account_id: accountId }),
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return (await response.json()) as Account;
}

export async function logout(): Promise<void> {
  const response = await fetch("/api/session", { method: "DELETE" });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
}
