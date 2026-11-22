export type Transaction = {
  id: number; date: string; merchant: string | null; description: string;
  category: string; type: "income" | "expense"; amount_minor: number; currency: "INR";
  needs_review: boolean;
};

export type TransactionPage = { items: Transaction[]; total: number; page: number; page_size: number };

export type Budget = {
  month: string; category: string; budget_minor: number;
  spent_minor: number | null; remaining_minor: number | null;
  utilization_percent: number | null; status: "insufficient_data" | "over_budget" | "within_budget";
};

export type BudgetSummary = {
  month: string; categories: string[]; budgets: Budget[]; has_imported_records: boolean;
  overall_utilization_percent: number | null; status: string;
};

export type Dashboard = {
  month: string; availability: "has_records" | "no_records"; currency: "INR";
  total_income_minor: number | null; total_expenses_minor: number | null;
  net_cash_flow_minor: number | null; transaction_count: number;
  category_totals_minor: Record<string, number>; budget_summary: BudgetSummary;
};

export type TrendRow = {
  month: string; status: "no_records" | "has_records"; total_income_minor: number | null;
  total_expenses_minor: number | null; net_cash_flow_minor: number | null;
};

export type Trends = { end_month: string | null; months: TrendRow[]; status: string };

export type Comparison = {
  month1: string; month2: string; month1_expenses_minor: number | null;
  month2_expenses_minor: number | null; absolute_difference_minor: number | null;
  change_percent: number | null; status: "increase" | "decrease" | "unchanged" | "insufficient_data";
  missing_months: string[];
};

export type Flag = { date: string; category: string; amount_minor: number; score: number; reason: string };
export type Anomalies = {
  status: string; note: string; reason?: string; flagged_count: number;
  minimum_history: number; threshold: number; baseline_start_month: string;
  categories: Record<string, { status: string; reason?: string; history_count: number }>;
  unusual_transactions: Flag[];
};

export type Savings = {
  status: string; comparison_month: string | null; comparison_status: string;
  observations: Array<{ category: string; type: string; evidence: Record<string, number | null>; suggested_action: string }>;
};

export type ImportResult = {
  total_rows: number; imported_rows: number; rejected_rows: number;
  uncategorized_transactions: number; potential_duplicates: number;
  already_imported: boolean; errors: Array<{ row: number; error: string }>;
};

export type ImportBatch = {
  id: number; file_name: string; imported_at: string; imported_rows: number;
  rejected_rows: number; total_rows: number; status: "imported" | "partial" | "rejected";
};

export type ChatMessage = { role: "user" | "assistant"; text: string };
export type ChatSession = { id: string; title: string; updated_at: number };
export type ChatHistory = ChatSession & { messages: ChatMessage[] };

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
  }
}

export function query(path: string, params: Record<string, string | number | undefined>) {
  const values = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") values.set(key, String(value));
  }
  const suffix = values.toString();
  return suffix ? `${path}?${suffix}` : path;
}

async function request(path: string, options: RequestInit = {}) {
  let response: Response;
  try {
    const headers = new Headers(options.headers);
    const method = options.method ?? "GET";
    if (method !== "GET" && path !== "/auth/login") {
      const session = await request("/auth/session", { signal: options.signal });
      const { csrf_token } = await session.json() as { csrf_token: string };
      headers.set("X-CSRF-Token", csrf_token);
    }
    response = await fetch(`/api${path}`, { cache: "no-store", ...options, headers });
  } catch (error) {
    if (options.signal?.aborted || error instanceof ApiError) throw error;
    throw new ApiError("Could not reach the local FinPilot API. Check that the backend is running.", 0);
  }
  if (!response.ok) {
    if (response.status === 401 && path !== "/auth/login" && typeof window !== "undefined") {
      window.dispatchEvent(new Event("finpilot:unauthenticated"));
    }
    const payload = await response.json().catch(() => null);
    throw new ApiError(payload?.error?.message ?? "The request failed. Please try again.", response.status);
  }
  return response;
}

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await request(path, options);
  if (response.status === 204) return undefined as T;
  return response.json();
}

export function jsonBody(value: unknown): RequestInit {
  return { headers: { "Content-Type": "application/json" }, body: JSON.stringify(value) };
}

export async function streamReply(
  session: string, message: string, onDelta: (text: string) => void, signal?: AbortSignal,
) {
  const response = await request(`/chat/sessions/${session}/messages`, {
    method: "POST", ...jsonBody({ message }), signal,
  });
  const reader = response.body?.getReader();
  if (!reader) throw new Error("The response stream is unavailable.");
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const event = frame.split("\n").find((line) => line.startsWith("event: "))?.slice(7);
        const data = frame.split("\n").find((line) => line.startsWith("data: "))?.slice(6);
        if (data) {
          const payload: { text?: string; message?: string } = JSON.parse(data);
          if (event === "delta" && payload.text) onDelta(payload.text);
          if (event === "done" && payload.text) return payload.text;
          if (event === "error") throw new ApiError(payload.message ?? "The assistant could not reply.", 503);
        }
        boundary = buffer.indexOf("\n\n");
      }
    }
    throw new Error("The reply ended unexpectedly. Please try again.");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
