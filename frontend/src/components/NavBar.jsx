import { NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function NavBar() {
  const { user, logout } = useAuth();
  if (!user) return null;

  return (
    <header className="navbar">
      <span className="navbar-brand">Enterprise Assistant</span>
      <nav className="navbar-links">
        <NavLink to="/requests" end>Requests</NavLink>
        {user.role === "admin" && <NavLink to="/approvals">Approvals</NavLink>}
        {user.role === "admin" && <NavLink to="/admin">Admin</NavLink>}
      </nav>
      <div className="navbar-user">
        <span>{user.full_name} <span className="user-role">({user.role})</span></span>
        <button type="button" onClick={logout}>Log out</button>
      </div>
    </header>
  );
}
