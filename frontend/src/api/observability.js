import client from "./client";

export async function fetchTraceSpans(requestId) {
  const { data } = await client.get("/api/admin/traces", {
    params: { request_id: requestId },
  });
  return data;
}

export async function fetchTraceTree(requestId) {
  const { data } = await client.get(`/api/admin/traces/${requestId}/tree`);
  return data;
}
