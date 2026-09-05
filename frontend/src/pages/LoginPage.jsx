import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { demoLogin } from "../api/auth";
import { useAuth } from "../context/AuthContext";

const DEMO_ROLES = [
  { role: "admin",    label: "Admin",    desc: "Full access: users, approvals, audit, settings" },
  { role: "hr",       label: "HR",       desc: "Requests + HR banner" },
  { role: "employee", label: "Employee", desc: "Submit and view own requests" },
];

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [demoLoading, setDemoLoading] = useState(null);
  const { login, loginWithToken } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      await login(email, password);
      navigate("/requests");
    } catch {
      setError("Incorrect email or password.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDemoLogin(role) {
    setError("");
    setDemoLoading(role);
    try {
      const { access_token } = await demoLogin(role);
      await loginWithToken(access_token);
      navigate("/requests");
    } catch {
      setError("Could not sign in to demo account.");
      setDemoLoading(null);
    }
  }

  return (
    <div className="auth-page">
      <h1>Sign in</h1>

      <div className="demo-login">
        <p className="demo-label">Quick demo login</p>
        <div className="demo-buttons">
          {DEMO_ROLES.map(({ role, label, desc }) => (
            <button
              key={role}
              type="button"
              className={`demo-btn demo-btn-${role}`}
              disabled={demoLoading !== null}
              onClick={() => handleDemoLogin(role)}
              title={desc}
            >
              {demoLoading === role ? "Signing in…" : label}
            </button>
          ))}
        </div>
      </div>

      <div className="auth-divider"><span>or sign in manually</span></div>

      <form onSubmit={handleSubmit}>
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Signing in..." : "Sign in"}
        </button>
      </form>
      <p>
        No account? <Link to="/register">Register</Link>
      </p>
    </div>
  );
}
