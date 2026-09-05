import client from "./client";

export async function listPendingApprovals() {
  const { data } = await client.get("/api/approvals");
  return data;
}

export async function getPendingCount() {
  const { data } = await client.get("/api/approvals/count");
  return data.count;
}

export async function approveSubtask(id) {
  const { data } = await client.post(`/api/approvals/${id}/approve`);
  return data;
}

export async function rejectSubtask(id, reason) {
  const { data } = await client.post(`/api/approvals/${id}/reject`, { reason });
  return data;
}
