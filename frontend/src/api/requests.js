import client from "./client";

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
