import type { ChatResponse, DocumentsResponse, TraceEvent } from "./types";

const BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiRequestError extends Error {
  code: string;
  requestId?: string;
  status: number;

  constructor(message: string, code = "error", status = 0, requestId?: string) {
    super(message);
    this.name = "ApiRequestError";
    this.code = code;
    this.status = status;
    this.requestId = requestId;
  }
}

function requestId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `req_${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
  }
  return `req_${Math.random().toString(36).slice(2, 14)}`;
}

async function toError(response: Response) {
  let code = "error";
  let message = `Request failed (${response.status})`;
  let rid: string | undefined;
  try {
    const body = await response.json();
    if (body?.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      rid = body.error.request_id;
    }
  } catch {
    /* non-JSON error body */
  }
  return new ApiRequestError(message, code, response.status, rid);
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Render's free tier sleeps; a first request can take ~30 s. Retry rather than fail. */
export async function getDocuments(attempts = 3): Promise<DocumentsResponse> {
  let lastError: unknown;
  for (let i = 0; i < attempts; i++) {
    try {
      const response = await fetch(`${BASE}/api/documents`, {
        headers: { "x-request-id": requestId() },
        cache: "no-store",
      });
      if (!response.ok) throw await toError(response);
      return (await response.json()) as DocumentsResponse;
    } catch (error) {
      lastError = error;
      if (i < attempts - 1) await sleep(1500 * (i + 1));
    }
  }
  throw lastError;
}

export async function pingHealth(timeoutMs = 45000): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${BASE}/api/health`, {
      signal: controller.signal,
      cache: "no-store",
    });
    return response.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

export async function postChat(
  body: { question: string; doc_id: string },
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const response = await fetch(`${BASE}/api/chat`, {
    method: "POST",
    headers: { "content-type": "application/json", "x-request-id": requestId() },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) throw await toError(response);
  return (await response.json()) as ChatResponse;
}

export interface StreamHandlers {
  onTrace?: (event: TraceEvent) => void;
  onToken?: (text: string) => void;
  onFinal?: (response: ChatResponse) => void;
  onError?: (error: ApiRequestError) => void;
}

/**
 * SSE over POST. EventSource cannot POST, so we read the body stream ourselves.
 */
export async function streamChat(
  body: { question: string; doc_id: string },
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "content-type": "application/json", "x-request-id": requestId() },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) throw await toError(response);
  if (!response.body) throw new ApiRequestError("The server sent no response body.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sawFinal = false;

  const dispatch = (frame: string) => {
    let event = "message";
    const dataLines: string[] = [];
    for (const line of frame.split("\n")) {
      // ": ping" comment lines are keep-alives and carry no payload.
      if (line.startsWith(":")) continue;
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (!dataLines.length) return;
    let payload: unknown;
    try {
      payload = JSON.parse(dataLines.join("\n"));
    } catch {
      return;
    }
    if (event === "trace") handlers.onTrace?.(payload as TraceEvent);
    else if (event === "token") handlers.onToken?.((payload as { text: string }).text);
    else if (event === "final") {
      sawFinal = true;
      handlers.onFinal?.(payload as ChatResponse);
    }
    else if (event === "error") {
      const e = payload as { message?: string; request_id?: string };
      handlers.onError?.(new ApiRequestError(e.message ?? "Stream error", "stream_error", 0, e.request_id));
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    // Normalise line endings BEFORE looking for frame boundaries. sse-starlette
    // separates events with "\r\n\r\n"; splitting on "\n\n" never matches it,
    // because a "\r" sits between the two newlines. The buffer then grows forever
    // and not a single event is ever dispatched - the server answers correctly and
    // the UI shows nothing at all.
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) if (frame.trim()) dispatch(frame);
  }
  if (buffer.trim()) dispatch(buffer);

  // Second line of defence. Streaming can also be defeated by a proxy that buffers
  // the response, which looks identical from here: the request succeeds and no
  // "final" ever arrives. Rather than leaving the user staring at a spinner, ask the
  // plain endpoint for the same answer.
  if (!sawFinal) {
    const fallback = await postChat(body, signal);
    handlers.onFinal?.(fallback);
  }
}
