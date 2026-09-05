import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import NavBar from "../components/NavBar";
import {
  getDecisionTrace,
  getLatestRagEvaluation,
  getMetrics,
  getPermissionsMatrix,
  getSettings,
  getSystemHealth,
  listAllRequests,
  listAuditLogs,
  listUsers,
  runRagEvaluation,
  togglePermission,
  updateSettings,
  updateUser,
} from "../api/admin";
import { useAuth } from "../context/AuthContext";
import { humanizeAgent, humanizeStatus } from "../utils/labels";

const EVENT_TYPES = ["", "agent_action", "data_access", "approval", "auth", "admin"];

function formatMetricValue(key, value) {
  if (value == null) return "—";
  if (typeof value === "object") {
    const entries = Object.entries(value);
    if (entries.length === 0) return "—";
    return entries.map(([k, v]) => `${humanizeAgent(k)}: ${formatMetricValue(key, v)}`).join(", ");
  }
  if (key.endsWith("_rate") || key.endsWith("_coverage") || key.includes("confidence")) {
    return `${Math.round(value * 100)}%`;
  }
  if (key.includes("_seconds")) {
    return `${value.toFixed(2)}s`;
  }
  if (typeof value === "number" && !Number.isInteger(value)) {
    return value.toFixed(2);
  }
  return String(value);
}

function humanizeMetricKey(key) {
  return key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

function renderAuditContext(entry) {
  if (!entry.context) return "—";
  if (entry.event_type === "data_access") {
    const sources = entry.context.sources ?? [];
    const sensitive = entry.context.sensitive;
    return (
      <span className="data-access-context">
        {sensitive && <span className="hitl-reason" style={{ marginRight: "6px", fontSize: "10px" }}>Sensitive</span>}
        <strong>Sources:</strong>{" "}
        {sources.length > 0 ? (
          <ul className="data-access-sources">
            {sources.map((s) => <li key={s}>{s}</li>)}
          </ul>
        ) : "none"}
      </span>
    );
  }
  return (
    <span className="audit-context">
      {JSON.stringify(entry.context)}
    </span>
  );
}

function isDenialRow(action) {
  return /\.(deny|denied|revoke)/.test(action);
}

function MetricsTable({ title, data }) {
  return (
    <div>
      <h3>{title}</h3>
      <table className="admin-table">
        <thead>
          <tr>
            <th>Metric</th>
            <th>Value</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(data).map(([key, value]) => (
            <tr key={key}>
              <td>{humanizeMetricKey(key)}</td>
              <td>{formatMetricValue(key, value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MetricsSection() {
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getMetrics().then(setReport).catch(() => setError("Could not load evaluation metrics."));
  }, []);

  if (error) {
    return (
      <section className="admin-section">
        <h2>Evaluation Metrics</h2>
        <p className="error">{error}</p>
      </section>
    );
  }
  if (!report) return null;

  return (
    <section className="admin-section">
      <h2>Evaluation Metrics</h2>
      <p className="subtask-explanation">
        Accuracy figures are confidence-based proxies (no labeled ground-truth dataset exists),
        not verified-correctness scores.
      </p>
      <div className="metrics-grid">
        <MetricsTable title="Accuracy" data={report.accuracy} />
        <MetricsTable title="Timing" data={report.timing} />
        <MetricsTable title="Security" data={report.security} />
        <MetricsTable title="Human-in-the-Loop" data={report.hitl} />
        <MetricsTable title="Explainability" data={report.explainability} />
      </div>
    </section>
  );
}

function RagEvaluationSection() {
  const [run, setRun] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getLatestRagEvaluation()
      .then(setRun)
      .catch(() => setError("Could not load the latest evaluation."));
  }, []);

  async function handleRun() {
    setRunning(true);
    setError("");
    try {
      const result = await runRagEvaluation();
      setRun(result);
    } catch {
      setError("Could not complete the evaluation run.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <section className="admin-section">
      <h2>RAG vs. Baseline (Hallucination Check)</h2>
      <p className="subtask-explanation">
        Each question has a company-specific fact invented for this project's seed documents --
        no LLM could know it without retrieval. "Baseline" calls the LLM directly with no
        context; "Grounded" uses the real RAG pipeline. A wide accuracy gap is a measurable
        hallucination-rate reduction attributable to RAG (NFR-2).
      </p>
      <button type="button" onClick={handleRun} disabled={running}>
        {running ? "Running (this takes a couple of minutes)..." : "Run Evaluation"}
      </button>
      {error && <p className="error">{error}</p>}
      {run && (
        <>
          <table className="admin-table" style={{ marginTop: "12px" }}>
            <thead>
              <tr>
                <th>Run at</th>
                <th>Baseline accuracy</th>
                <th>Grounded accuracy</th>
                <th>Improvement</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{new Date(run.created_at).toLocaleString()}</td>
                <td>{Math.round(run.baseline_accuracy * 100)}%</td>
                <td>{Math.round(run.grounded_accuracy * 100)}%</td>
                <td>
                  +{Math.round((run.grounded_accuracy - run.baseline_accuracy) * 100)}
                  pts
                </td>
              </tr>
            </tbody>
          </table>
          <table className="admin-table" style={{ marginTop: "12px" }}>
            <thead>
              <tr>
                <th>Question</th>
                <th>Expected keywords</th>
                <th>Baseline answer</th>
                <th>Grounded answer</th>
                <th>Sources</th>
              </tr>
            </thead>
            <tbody>
              {run.cases.map((c) => (
                <tr key={c.question}>
                  <td>{c.question}</td>
                  <td>
                    <span className="keyword-list">
                      {(c.expected_keywords ?? []).map((kw) => (
                        <code key={kw} className="keyword-chip">{kw}</code>
                      ))}
                    </span>
                  </td>
                  <td className={c.baseline_correct ? "confidence-high" : "confidence-low"}>
                    {c.baseline_answer}
                  </td>
                  <td className={c.grounded_correct ? "confidence-high" : "confidence-low"}>
                    {c.grounded_answer}
                  </td>
                  <td>{c.grounded_sources.join(", ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {!run && !error && <p>No evaluation has been run yet.</p>}
    </section>
  );
}

function SystemHealthSection() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getSystemHealth().then(setHealth).catch(() => setError("Could not load system health."));
  }, []);

  if (error) return <section className="admin-section"><h2>System Health</h2><p className="error">{error}</p></section>;
  if (!health) return null;

  return (
    <section className="admin-section">
      <h2>System Health</h2>
      <div className="metrics-grid">
        <div>
          <h3>Database</h3>
          <table className="admin-table">
            <tbody>
              <tr><td>Status</td><td><span className="status status-completed">{health.db.status}</span></td></tr>
              <tr><td>Users</td><td>{health.db.user_count} ({health.db.active_user_count} active)</td></tr>
              <tr><td>Permissions</td><td>{health.db.permission_count} rules</td></tr>
            </tbody>
          </table>
        </div>
        <div>
          <h3>RAG / ChromaDB</h3>
          <table className="admin-table">
            <tbody>
              <tr>
                <td>Status</td>
                <td>
                  <span className={`status ${health.rag.status === "ok" ? "status-completed" : "status-failed"}`}>
                    {health.rag.status}
                  </span>
                </td>
              </tr>
              <tr><td>Documents</td><td>{health.rag.document_count}</td></tr>
            </tbody>
          </table>
        </div>
        <div>
          <h3>Agents</h3>
          <table className="admin-table">
            <tbody>
              {health.agents.map((a) => (
                <tr key={a.type}>
                  <td>{humanizeAgent(a.type)}</td>
                  <td>
                    <span className="status status-completed">registered</span>
                    {a.sensitive && <span className="hitl-reason" style={{ marginLeft: "6px" }}>HITL always</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

function SettingsSection() {
  const [threshold, setThreshold] = useState(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getSettings().then((s) => {
      setThreshold(s.hitl_confidence_threshold);
      setDraft(String(Math.round(s.hitl_confidence_threshold * 100)));
    }).catch(() => setError("Could not load settings."));
  }, []);

  async function handleSave(e) {
    e.preventDefault();
    const val = parseFloat(draft) / 100;
    if (Number.isNaN(val) || val < 0 || val > 1) {
      setError("Enter a value between 0 and 100.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const updated = await updateSettings({ hitl_confidence_threshold: val });
      setThreshold(updated.hitl_confidence_threshold);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch {
      setError("Could not save settings.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="admin-section">
      <h2>Settings</h2>
      <p className="subtask-explanation">
        HITL confidence threshold: subtasks with confidence below this value are automatically
        escalated to human review. Default is 50%. Resets to 50% on server restart.
      </p>
      {error && <p className="error">{error}</p>}
      {threshold !== null && (
        <form onSubmit={handleSave} style={{ display: "flex", alignItems: "center", gap: "10px", marginTop: "8px" }}>
          <label style={{ fontSize: "14px" }}>
            HITL threshold (%)
            <input
              type="number"
              min="0"
              max="100"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              style={{ width: "80px", marginLeft: "8px" }}
            />
          </label>
          <button type="submit" disabled={saving}>{saving ? "Saving..." : "Save"}</button>
          {saved && <span style={{ color: "#16a34a", fontSize: "13px" }}>Saved</span>}
        </form>
      )}
    </section>
  );
}

function AllRequestsSection() {
  const [requests, setRequests] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    listAllRequests().then(setRequests).catch(() => setError("Could not load requests."));
  }, []);

  return (
    <section className="admin-section">
      <h2>All Requests</h2>
      <p className="subtask-explanation">All requests across every user, newest first.</p>
      {error && <p className="error">{error}</p>}
      <table className="admin-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Requester</th>
            <th>Request text</th>
            <th>Status</th>
            <th>Subtasks</th>
            <th>Submitted</th>
            <th>Completed</th>
          </tr>
        </thead>
        <tbody>
          {requests.map((r) => (
            <tr key={r.id}>
              <td>
                <Link to={`/requests/${r.id}`} style={{ color: "var(--accent)", textDecoration: "none" }}>
                  #{r.id}
                </Link>
              </td>
              <td>{r.requester_email}</td>
              <td className="request-cell-text">{r.text}</td>
              <td><span className={`status status-${r.status}`}>{humanizeStatus(r.status)}</span></td>
              <td>{r.subtask_count}</td>
              <td>{new Date(r.created_at).toLocaleString()}</td>
              <td>{r.completed_at ? new Date(r.completed_at).toLocaleString() : "—"}</td>
            </tr>
          ))}
          {requests.length === 0 && !error && (
            <tr><td colSpan={7} style={{ color: "var(--text)" }}>No requests yet.</td></tr>
          )}
        </tbody>
      </table>
    </section>
  );
}

function UsersSection({ currentUserId, roles }) {
  const [users, setUsers] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    listUsers().then(setUsers).catch(() => setError("Could not load users."));
  }, []);

  async function handleRoleChange(user, role) {
    try {
      const updated = await updateUser(user.id, { role });
      setUsers((prev) => prev.map((u) => (u.id === user.id ? updated : u)));
    } catch {
      setError(`Could not update role for ${user.email}.`);
    }
  }

  async function handleActiveToggle(user) {
    try {
      const updated = await updateUser(user.id, { is_active: !user.is_active });
      setUsers((prev) => prev.map((u) => (u.id === user.id ? updated : u)));
    } catch {
      setError(`Could not update status for ${user.email}.`);
    }
  }

  return (
    <section className="admin-section">
      <h2>Users</h2>
      {error && <p className="error">{error}</p>}
      <table className="admin-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Email</th>
            <th>Name</th>
            <th>Role</th>
            <th>Active</th>
            <th>Joined</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td style={{ color: "var(--text)", fontSize: "12px" }}>#{u.id}</td>
              <td>{u.email}</td>
              <td>{u.full_name}</td>
              <td>
                <select
                  value={u.role}
                  disabled={u.id === currentUserId}
                  onChange={(e) => handleRoleChange(u, e.target.value)}
                >
                  {roles.map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </td>
              <td>
                <input
                  type="checkbox"
                  checked={u.is_active}
                  disabled={u.id === currentUserId}
                  onChange={() => handleActiveToggle(u)}
                />
              </td>
              <td style={{ fontSize: "12px", color: "var(--text)" }}>
                {new Date(u.created_at).toLocaleDateString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function PermissionsSection() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getPermissionsMatrix().then(setData).catch(() => setError("Could not load permissions."));
  }, []);

  async function handleToggle(role, agentType, allowed) {
    try {
      const updated = await togglePermission(role, agentType, allowed);
      setData(updated);
    } catch {
      setError("Could not update this permission.");
    }
  }

  if (!data) return <section className="admin-section"><h2>Permissions</h2>{error && <p className="error">{error}</p>}</section>;

  return (
    <section className="admin-section">
      <h2>Permissions</h2>
      {error && <p className="error">{error}</p>}
      <table className="admin-table">
        <thead>
          <tr>
            <th>Agent</th>
            {data.roles.map((role) => (
              <th key={role}>{role}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.agent_types.map((agentType) => (
            <tr key={agentType}>
              <td>{humanizeAgent(agentType)}</td>
              {data.roles.map((role) => {
                const allowed = data.matrix[role]?.includes(agentType);
                return (
                  <td key={role}>
                    <input
                      type="checkbox"
                      checked={allowed}
                      onChange={() => handleToggle(role, agentType, !allowed)}
                    />
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function AuditLogSection({ onTrace }) {
  const [logs, setLogs] = useState([]);
  const [users, setUsers] = useState([]);
  const [eventType, setEventType] = useState("");
  const [userId, setUserId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    listUsers().then(setUsers).catch(() => {});
  }, []);

  useEffect(() => {
    listAuditLogs(eventType || undefined, userId || undefined)
      .then(setLogs)
      .catch(() => setError("Could not load audit logs."));
  }, [eventType, userId]);

  return (
    <section className="admin-section">
      <h2>Audit Log</h2>
      <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", marginBottom: "12px" }}>
        <label className="audit-filter">
          Event type
          <select value={eventType} onChange={(e) => setEventType(e.target.value)}>
            {EVENT_TYPES.map((t) => (
              <option key={t} value={t}>
                {t || "All"}
              </option>
            ))}
          </select>
        </label>
        <label className="audit-filter">
          Filter by user
          <select value={userId} onChange={(e) => setUserId(e.target.value)}>
            <option value="">All users</option>
            {users.map((u) => (
              <option key={u.id} value={String(u.id)}>
                {u.email}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && <p className="error">{error}</p>}
      <table className="admin-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Type</th>
            <th>Action</th>
            <th>User</th>
            <th>Role</th>
            <th>Request</th>
            <th>Subtask</th>
            <th>Context</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {logs.map((log) => (
            <tr key={log.id} className={isDenialRow(log.action) ? "audit-row-denial" : ""}>
              <td>{new Date(log.created_at).toLocaleString()}</td>
              <td>
                <span className={`audit-type-badge audit-type-${log.event_type}`}>
                  {log.event_type}
                </span>
              </td>
              <td>{log.action}</td>
              <td>{log.user_email ?? "—"}</td>
              <td>{log.role ?? "—"}</td>
              <td>
                {log.request_id != null ? (
                  <Link
                    to={`/requests/${log.request_id}`}
                    style={{ color: "var(--accent)", textDecoration: "none" }}
                  >
                    #{log.request_id}
                  </Link>
                ) : "—"}
              </td>
              <td>
                {log.subtask_id != null ? (
                  <button
                    type="button"
                    className="trace-inline-btn"
                    onClick={() => onTrace(log.subtask_id)}
                    title="Trace this subtask"
                  >
                    #{log.subtask_id}
                  </button>
                ) : "—"}
              </td>
              <td>{renderAuditContext(log)}</td>
              <td>
                {log.subtask_id != null && (
                  <button type="button" onClick={() => onTrace(log.subtask_id)}>
                    Trace
                  </button>
                )}
              </td>
            </tr>
          ))}
          {logs.length === 0 && (
            <tr>
              <td colSpan={9}>No audit log entries.</td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}

function TraceSection({ requestedSubtaskId, requestNonce }) {
  const [subtaskIdInput, setSubtaskIdInput] = useState("");
  const [trace, setTrace] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const sectionRef = useRef(null);

  async function lookup(id) {
    if (!id) return;
    setLoading(true);
    setError("");
    try {
      const result = await getDecisionTrace(id);
      setTrace(result);
    } catch {
      setError(`Could not find a trace for subtask ${id}.`);
      setTrace(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (requestedSubtaskId != null) {
      setSubtaskIdInput(String(requestedSubtaskId));
      lookup(requestedSubtaskId);
      sectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedSubtaskId, requestNonce]);

  function handleSubmit(event) {
    event.preventDefault();
    lookup(subtaskIdInput);
  }

  return (
    <section className="admin-section" ref={sectionRef}>
      <h2>Trace a Decision</h2>
      <p className="subtask-explanation">
        Assembles the full causal trail for one subtask -- its own rationale/confidence, the
        request that produced it, and every audit log entry tied to it, in order (NFR-3).
      </p>
      <form onSubmit={handleSubmit} className="trace-lookup">
        <input
          type="number"
          value={subtaskIdInput}
          onChange={(e) => setSubtaskIdInput(e.target.value)}
          placeholder="Subtask ID"
        />
        <button type="submit" disabled={loading}>
          {loading ? "Looking up..." : "Look Up"}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      {trace && (
        <>
          <table className="admin-table">
            <tbody>
              <tr>
                <td>Subtask</td>
                <td>
                  <span className="subtask-id-badge">#{trace.subtask.id}</span>
                  {" "}{humanizeAgent(trace.subtask.agent_type)}
                </td>
              </tr>
              <tr>
                <td>Request</td>
                <td>
                  <Link
                    to={`/requests/${trace.request.id}`}
                    style={{ color: "var(--accent)", textDecoration: "none" }}
                  >
                    #{trace.request.id}
                  </Link>
                  {" — "}&quot;{trace.request.text}&quot;
                </td>
              </tr>
              <tr>
                <td>Requester</td>
                <td>{trace.request.requester_email}</td>
              </tr>
              <tr>
                <td>Status</td>
                <td>
                  <span className={`status status-${trace.subtask.status}`}>
                    {humanizeStatus(trace.subtask.status)}
                  </span>
                </td>
              </tr>
              <tr>
                <td>Confidence</td>
                <td>
                  {trace.subtask.confidence != null
                    ? `${Math.round(trace.subtask.confidence * 100)}%`
                    : "—"}
                </td>
              </tr>
              <tr>
                <td>Result</td>
                <td style={{ whiteSpace: "pre-line" }}>{trace.subtask.result}</td>
              </tr>
              <tr>
                <td>Explanation</td>
                <td>{trace.subtask.explanation}</td>
              </tr>
              {trace.subtask.approved_by_email && (
                <tr>
                  <td>Reviewed by</td>
                  <td>
                    {trace.subtask.approved_by_email} at{" "}
                    {new Date(trace.subtask.approved_at).toLocaleString()}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <h3 style={{ marginTop: "1rem" }}>Audit Trail</h3>
          <table className="admin-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Type</th>
                <th>Action</th>
                <th>Role</th>
                <th>Context</th>
              </tr>
            </thead>
            <tbody>
              {trace.audit_trail.map((entry) => (
                <tr key={entry.id} className={isDenialRow(entry.action) ? "audit-row-denial" : ""}>
                  <td>{new Date(entry.created_at).toLocaleString()}</td>
                  <td>
                    <span className={`audit-type-badge audit-type-${entry.event_type}`}>
                      {entry.event_type}
                    </span>
                  </td>
                  <td>{entry.action}</td>
                  <td>{entry.role ?? "—"}</td>
                  <td>{renderAuditContext(entry)}</td>
                </tr>
              ))}
              {trace.audit_trail.length === 0 && (
                <tr>
                  <td colSpan={5}>No audit log entries for this subtask.</td>
                </tr>
              )}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

export default function AdminPage() {
  const { user } = useAuth();
  const location = useLocation();
  const [traceRequest, setTraceRequest] = useState({ subtaskId: null, nonce: 0 });
  const [roles, setRoles] = useState(["employee", "hr", "admin"]);

  useEffect(() => {
    getPermissionsMatrix()
      .then((data) => setRoles(data.roles))
      .catch(() => {});
  }, []);

  // Support navigating here with a pre-filled trace (e.g. from ApprovalsPage)
  useEffect(() => {
    if (location.state?.traceSubtaskId != null) {
      setTraceRequest({ subtaskId: location.state.traceSubtaskId, nonce: Date.now() });
    }
  }, [location.state]);

  if (user && user.role !== "admin") {
    return <Navigate to="/requests" replace />;
  }

  function handleTrace(subtaskId) {
    setTraceRequest({ subtaskId, nonce: Date.now() });
  }

  return (
    <div className="requests-page">
      <NavBar />
      <div className="page-content">
        {user && (
          <>
            <SystemHealthSection />
            <SettingsSection />
            <AllRequestsSection />
            <UsersSection currentUserId={user.id} roles={roles} />
            <PermissionsSection />
            <AuditLogSection onTrace={handleTrace} />
            <TraceSection
              requestedSubtaskId={traceRequest.subtaskId}
              requestNonce={traceRequest.nonce}
            />
            <MetricsSection />
            <RagEvaluationSection />
          </>
        )}
      </div>
    </div>
  );
}
