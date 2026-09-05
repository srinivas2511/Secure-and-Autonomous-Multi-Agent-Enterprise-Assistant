import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { getPendingCount } from "../api/approvals";
import { useAuth } from "../context/AuthContext";

export default function NavBar() {
  const { user, logout } = useAuth();
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    if (user?.role !== "admin") return;
    function fetchCount() {
      getPendingCount().then(setPendingCount).catch(() => {});
    }
    fetchCount();
    const timer = setInterval(fetchCount, 30000);
    return () => clearInterval(timer);
  }, [user]);

  if (!user) return null;

  return (
    <header className="navbar">
      <span className="navbar-brand">Enterprise Assistant</span>
      <nav className="navbar-links">
        <NavLink to="/requests" end>Requests</NavLink>
        {user.role === "admin" && (
          <NavLink to="/approvals">
            Approvals
            {pendingCount > 0 && (
              <span className="nav-badge">{pendingCount}</span>
            )}
          </NavLink>
        )}
        {user.role === "admin" && <NavLink to="/admin">Admin</NavLink>}
      </nav>
      <div className="navbar-user">
        <span>{user.full_name} <span className="user-role">({user.role})</span></span>
        <button type="button" onClick={logout}>Log out</button>
      </div>
    </header>
  );
}
