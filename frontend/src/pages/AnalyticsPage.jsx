import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, LineChart, Line, AreaChart, Area,
} from "recharts";
import NavBar from "../components/NavBar";
import { getAnalytics } from "../api/admin";
import { useAuth } from "../context/AuthContext";
import { humanizeAgent, humanizeStatus } from "../utils/labels";

// ── Palette ───────────────────────────────────────────────────────────────────
const AGENT_COLORS = {
  rag:        "#6366f1",
  security:   "#ef4444",
  analytics:  "#f59e0b",
  workflow:   "#10b981",
  validation: "#3b82f6",
};
const AGENT_COLOR_LIST = Object.values(AGENT_COLORS);

const STATUS_COLORS = {
  completed:        "#10b981",
  failed:           "#ef4444",
  pending_approval: "#f59e0b",
  pending:          "#94a3b8",
  processing:       "#3b82f6",
  partially_denied: "#f97316",
};

const DEPT_COLORS = ["#6366f1","#3b82f6","#10b981","#f59e0b","#ef4444"];

function agentColor(agent) {
  return AGENT_COLORS[agent] ?? "#94a3b8";
}

// ── Stat tile ─────────────────────────────────────────────────────────────────
function StatTile({ label, value, sub }) {
  return (
    <div className="analytics-stat">
      <span className="analytics-stat-value">{value}</span>
      <span className="analytics-stat-label">{label}</span>
      {sub && <span className="analytics-stat-sub">{sub}</span>}
    </div>
  );
}

// ── Section wrapper ───────────────────────────────────────────────────────────
function Section({ title, children }) {
  return (
    <section className="analytics-section">
      <h2 className="analytics-section-title">{title}</h2>
      {children}
    </section>
  );
}

// ── Custom tooltip ────────────────────────────────────────────────────────────
function ChartTooltip({ active, payload, label, formatter }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      {label && <p className="chart-tooltip-label">{label}</p>}
      {payload.map((p) => (
        <p key={p.dataKey} style={{ color: p.color ?? p.fill }}>
          {p.name ?? p.dataKey}: {formatter ? formatter(p.value, p.name) : p.value}
        </p>
      ))}
    </div>
  );
}

function usd(n) {
  return `$${n.toLocaleString()}`;
}

function pct(n) {
  return `${n}%`;
}

// ── Abbreviated date label (e.g. "Sep 28") ───────────────────────────────────
function shortDate(iso) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// ── Every-N-th tick to avoid overlap ─────────────────────────────────────────
function sparseTickFormatter(value, index, data, every = 7) {
  if (index % every !== 0) return "";
  return shortDate(value);
}

export default function AnalyticsPage() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getAnalytics()
      .then(setData)
      .catch(() => setError("Could not load analytics data."))
      .finally(() => setLoading(false));
  }, []);

  if (user && user.role !== "admin") return <Navigate to="/requests" replace />;

  const reload = () => {
    setLoading(true);
    setError("");
    getAnalytics().then(setData).catch(() => setError("Could not reload.")).finally(() => setLoading(false));
  };

  return (
    <div className="requests-page">
      <NavBar />
      <div className="page-content analytics-page">
        <div className="analytics-header">
          <h1>Analytics</h1>
          <button type="button" onClick={reload} disabled={loading} className="analytics-refresh">
            {loading ? "Loading…" : "Refresh"}
          </button>
        </div>

        {error && <p className="error">{error}</p>}

        {data && (
          <>
            {/* ── KPI row ─────────────────────────────────────────────── */}
            <div className="analytics-stats-row">
              <StatTile label="Total requests" value={data.total_requests} />
              <StatTile label="Total subtasks" value={data.total_subtasks} />
              <StatTile label="HITL escalations" value={data.hitl_escalations}
                sub={data.total_subtasks > 0
                  ? `${Math.round(data.hitl_escalations / data.total_subtasks * 100)}% of subtasks`
                  : null} />
              <StatTile label="Denials" value={data.denial_count} />
              <StatTile label="RAG knowledge base"
                value={`${data.enterprise?.headcount?.reduce((s, d) => s + d.count, 0) ?? "—"}`}
                sub="total headcount" />
            </div>

            {/* ── Request volume ───────────────────────────────────────── */}
            <Section title="Request volume — last 30 days">
              <div className="chart-container">
                <ResponsiveContainer width="100%" height={220}>
                  <AreaChart data={data.requests_by_day} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                    <defs>
                      <linearGradient id="reqGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                    <XAxis dataKey="date"
                      tickFormatter={(v, i) => sparseTickFormatter(v, i, data.requests_by_day, 5)}
                      tick={{ fontSize: 11, fill: "var(--chart-label)" }}
                      axisLine={false} tickLine={false} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "var(--chart-label)" }}
                      axisLine={false} tickLine={false} width={28} />
                    <Tooltip content={<ChartTooltip formatter={(v) => `${v} request${v !== 1 ? "s" : ""}`} />} />
                    <Area type="monotone" dataKey="count" name="Requests"
                      stroke="#6366f1" fill="url(#reqGrad)" strokeWidth={2} dot={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Section>

            {/* ── Status + agent usage row ─────────────────────────────── */}
            <div className="analytics-two-col">
              <Section title="Request status breakdown">
                <div className="chart-container chart-container--short">
                  <ResponsiveContainer width="100%" height={220}>
                    <PieChart>
                      <Pie
                        data={Object.entries(data.requests_by_status).map(([k, v]) => ({
                          name: humanizeStatus(k), value: v, key: k,
                        }))}
                        cx="50%" cy="50%" innerRadius={55} outerRadius={85}
                        dataKey="value" paddingAngle={2}
                      >
                        {Object.entries(data.requests_by_status).map(([k]) => (
                          <Cell key={k} fill={STATUS_COLORS[k] ?? "#94a3b8"} />
                        ))}
                      </Pie>
                      <Tooltip content={<ChartTooltip />} />
                      <Legend iconType="circle" iconSize={8}
                        formatter={(v) => <span style={{ fontSize: 12, color: "var(--chart-label)" }}>{v}</span>} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </Section>

              <Section title="Subtasks by agent">
                <div className="chart-container chart-container--short">
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={data.subtasks_by_agent.map(d => ({ ...d, agent: humanizeAgent(d.agent) }))}
                      margin={{ top: 8, right: 16, bottom: 8, left: 0 }} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" horizontal={false} />
                      <XAxis type="number" allowDecimals={false}
                        tick={{ fontSize: 11, fill: "var(--chart-label)" }} axisLine={false} tickLine={false} />
                      <YAxis type="category" dataKey="agent" width={80}
                        tick={{ fontSize: 11, fill: "var(--chart-label)" }} axisLine={false} tickLine={false} />
                      <Tooltip content={<ChartTooltip />} />
                      <Bar dataKey="count" name="Subtasks" radius={[0, 4, 4, 0]}>
                        {data.subtasks_by_agent.map((d) => (
                          <Cell key={d.agent} fill={agentColor(d.agent)} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Section>
            </div>

            {/* ── Confidence + duration row ────────────────────────────── */}
            <div className="analytics-two-col">
              <Section title="Confidence distribution">
                <div className="chart-container chart-container--short">
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={data.confidence_bins}
                      margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                      <XAxis dataKey="range" tick={{ fontSize: 11, fill: "var(--chart-label)" }}
                        axisLine={false} tickLine={false} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "var(--chart-label)" }}
                        axisLine={false} tickLine={false} width={28} />
                      <Tooltip content={<ChartTooltip />} />
                      <Bar dataKey="count" name="Subtasks" fill="#6366f1" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Section>

              <Section title="Avg confidence by agent">
                <div className="chart-container chart-container--short">
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart
                      data={data.avg_confidence_by_agent.map(d => ({ ...d, agent: humanizeAgent(d.agent) }))}
                      margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                      <XAxis dataKey="agent" tick={{ fontSize: 11, fill: "var(--chart-label)" }}
                        axisLine={false} tickLine={false} />
                      <YAxis domain={[0, 100]} tickFormatter={pct}
                        tick={{ fontSize: 11, fill: "var(--chart-label)" }}
                        axisLine={false} tickLine={false} width={36} />
                      <Tooltip content={<ChartTooltip formatter={pct} />} />
                      <Bar dataKey="avg_pct" name="Avg confidence" radius={[4, 4, 0, 0]}>
                        {data.avg_confidence_by_agent.map((d) => (
                          <Cell key={d.agent} fill={agentColor(
                            Object.keys(AGENT_COLORS).find(k => humanizeAgent(k) === d.agent) ?? d.agent
                          )} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Section>
            </div>

            {/* ── Avg duration by agent ────────────────────────────────── */}
            {data.avg_duration_by_agent.length > 0 && (
              <Section title="Avg response time by agent (ms)">
                <div className="chart-container">
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart
                      data={data.avg_duration_by_agent.map(d => ({ ...d, agent: humanizeAgent(d.agent) }))}
                      margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                      <XAxis dataKey="agent" tick={{ fontSize: 11, fill: "var(--chart-label)" }}
                        axisLine={false} tickLine={false} />
                      <YAxis tick={{ fontSize: 11, fill: "var(--chart-label)" }}
                        axisLine={false} tickLine={false} width={48}
                        tickFormatter={(v) => v >= 1000 ? `${(v/1000).toFixed(1)}s` : `${v}ms`} />
                      <Tooltip content={<ChartTooltip formatter={(v) => `${v} ms`} />} />
                      <Bar dataKey="avg_ms" name="Avg ms" radius={[4, 4, 0, 0]}>
                        {data.avg_duration_by_agent.map((d) => (
                          <Cell key={d.agent} fill={agentColor(
                            Object.keys(AGENT_COLORS).find(k => humanizeAgent(k) === d.agent) ?? d.agent
                          )} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Section>
            )}

            {/* ── Enterprise data ──────────────────────────────────────── */}
            <div className="analytics-two-col">
              <Section title="Headcount by department">
                <div className="chart-container chart-container--short">
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={data.enterprise.headcount}
                      margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                      <XAxis dataKey="dept" tick={{ fontSize: 11, fill: "var(--chart-label)" }}
                        axisLine={false} tickLine={false} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "var(--chart-label)" }}
                        axisLine={false} tickLine={false} width={28} />
                      <Tooltip content={<ChartTooltip formatter={(v) => `${v} people`} />} />
                      <Bar dataKey="count" name="Headcount" radius={[4, 4, 0, 0]}>
                        {data.enterprise.headcount.map((d, i) => (
                          <Cell key={d.dept} fill={DEPT_COLORS[i % DEPT_COLORS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Section>

              <Section title="Monthly expenses by department">
                <div className="chart-container chart-container--short">
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={data.enterprise.expenses}
                      margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                      <XAxis dataKey="dept" tick={{ fontSize: 11, fill: "var(--chart-label)" }}
                        axisLine={false} tickLine={false} />
                      <YAxis tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`}
                        tick={{ fontSize: 11, fill: "var(--chart-label)" }}
                        axisLine={false} tickLine={false} width={44} />
                      <Tooltip content={<ChartTooltip formatter={usd} />} />
                      <Bar dataKey="usd" name="Expenses" radius={[4, 4, 0, 0]}>
                        {data.enterprise.expenses.map((d, i) => (
                          <Cell key={d.dept} fill={DEPT_COLORS[i % DEPT_COLORS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Section>
            </div>

            {/* ── Top requesters ───────────────────────────────────────── */}
            {data.top_requesters.length > 0 && (
              <Section title="Top requesters">
                <table className="admin-table analytics-table">
                  <thead>
                    <tr><th>User</th><th>Requests</th></tr>
                  </thead>
                  <tbody>
                    {data.top_requesters.map((r) => (
                      <tr key={r.email}>
                        <td>{r.email}</td>
                        <td>{r.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Section>
            )}
          </>
        )}

        {loading && !data && (
          <p style={{ color: "var(--text-muted)", marginTop: "2rem" }}>Loading analytics…</p>
        )}
      </div>
    </div>
  );
}
