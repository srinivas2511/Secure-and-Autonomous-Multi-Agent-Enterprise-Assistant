import client from "./client";

export async function listUsers() {
  const { data } = await client.get("/api/admin/users");
  return data;
}

export async function updateUser(id, payload) {
  const { data } = await client.patch(`/api/admin/users/${id}`, payload);
  return data;
}

export async function getPermissionsMatrix() {
  const { data } = await client.get("/api/admin/permissions");
  return data;
}

export async function togglePermission(role, agentType, allowed) {
  const { data } = await client.post("/api/admin/permissions/toggle", {
    role,
    agent_type: agentType,
    allowed,
  });
  return data;
}

export async function listAuditLogs(eventType, userId) {
  const params = {};
  if (eventType) params.event_type = eventType;
  if (userId) params.user_id = userId;
  const { data } = await client.get("/api/admin/audit-logs", { params });
  return data;
}

export async function getMetrics() {
  const { data } = await client.get("/api/admin/metrics");
  return data;
}

export async function getLatestRagEvaluation() {
  const { data } = await client.get("/api/admin/rag-evaluation");
  return data;
}

export async function runRagEvaluation() {
  // No client-side timeout override needed -- axios defaults to none, and
  // this call realistically takes a couple of minutes (~12 real LLM calls).
  const { data } = await client.post("/api/admin/rag-evaluation/run");
  return data;
}

export async function getDecisionTrace(subtaskId) {
  const { data } = await client.get(`/api/admin/trace/${subtaskId}`);
  return data;
}

export async function getSystemHealth() {
  const { data } = await client.get("/api/admin/system-health");
  return data;
}

export async function getSettings() {
  const { data } = await client.get("/api/admin/settings");
  return data;
}

export async function updateSettings(payload) {
  const { data } = await client.patch("/api/admin/settings", payload);
  return data;
}
