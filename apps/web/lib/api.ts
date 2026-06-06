const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

export type ApiError = {
  status: number;
  message: string;
};

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    throw {
      status: response.status,
      message: await response.text(),
    } satisfies ApiError;
  }
  return response.json() as Promise<T>;
}

export async function apiSend<T>(method: "POST" | "PATCH" | "DELETE", path: string, body?: unknown) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    throw {
      status: response.status,
      message: await response.text(),
    } satisfies ApiError;
  }
  return response.json() as Promise<T>;
}

export async function apiSendText<T>(method: "POST", path: string, body: string, mediaType: string) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: { "Content-Type": mediaType, Accept: "application/json" },
    body,
  });
  if (!response.ok) {
    throw {
      status: response.status,
      message: await response.text(),
    } satisfies ApiError;
  }
  return response.json() as Promise<T>;
}
