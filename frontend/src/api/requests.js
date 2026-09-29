import client from "./client";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8123";

export async function createRequest(text) {
  const { data } = await client.post("/api/requests", { text });
  return data;
}

export async function listRequests() {
  const { data } = await client.get("/api/requests");
  return data;
}

export async function getRequest(id) {
  const { data } = await client.get(`/api/requests/${id}`);
  return data;
}

/**
 * Opens an SSE stream for a single request and calls onUpdate with each
 * parsed event payload until the request reaches a terminal status or the
 * caller aborts via the returned cleanup function.
 *
 * Returns a cleanup function — call it to close the stream early.
 */
export function streamRequest(requestId, onUpdate, onError) {
  const token = localStorage.getItem("access_token");
  const url = `${API_URL}/api/requests/stream/${requestId}`;

  const evtSource = new EventSource(
    token ? `${url}?token=${encodeURIComponent(token)}` : url
  );

  evtSource.onmessage = (evt) => {
    try {
      const payload = JSON.parse(evt.data);
      onUpdate(payload);
      const terminal = ["completed", "failed", "approved", "rejected"];
      if (terminal.includes(payload.status)) {
        evtSource.close();
      }
    } catch {
      // ignore parse errors from keep-alive blank lines
    }
  };

  evtSource.onerror = () => {
    evtSource.close();
    if (onError) onError();
  };

  return () => evtSource.close();
}
