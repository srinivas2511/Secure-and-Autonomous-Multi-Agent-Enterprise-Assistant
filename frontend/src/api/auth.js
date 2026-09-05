import client from "./client";

export async function register({ email, password, fullName }) {
  const { data } = await client.post("/api/auth/register", {
    email,
    password,
    full_name: fullName,
  });
  return data;
}

export async function login({ email, password }) {
  const form = new URLSearchParams();
  form.set("username", email);
  form.set("password", password);
  const { data } = await client.post("/api/auth/login", form, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  return data;
}

export async function fetchCurrentUser() {
  const { data } = await client.get("/api/auth/me");
  return data;
}

export async function demoLogin(role) {
  const { data } = await client.post("/api/auth/demo-login", { role });
  return data;
}
