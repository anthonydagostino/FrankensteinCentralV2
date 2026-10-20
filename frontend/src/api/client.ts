export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function handle<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(resp.status, detail);
  }
  return (await resp.json()) as T;
}

export async function getJson<T>(url: string): Promise<T> {
  const resp = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
  return handle<T>(resp);
}

export async function sendJson<T>(url: string, method: "POST" | "DELETE" | "PUT", body?: unknown): Promise<T> {
  const resp = await fetch(url, {
    method,
    credentials: "same-origin",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return handle<T>(resp);
}
