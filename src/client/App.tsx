import { Navigate, Route, Routes } from "react-router-dom";
import { Landing } from "./screens/Landing";
import { Intake } from "./screens/Intake";
import { Session } from "./screens/Session";
import { AdminSessions } from "./screens/AdminSessions";
import { AdminSessionDetail } from "./screens/AdminSessionDetail";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/new" element={<Intake />} />
      <Route path="/session/:id" element={<Session />} />
      <Route path="/admin" element={<Navigate to="/admin/sessions" replace />} />
      <Route path="/admin/sessions" element={<AdminSessions />} />
      <Route path="/admin/sessions/:id" element={<AdminSessionDetail />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
