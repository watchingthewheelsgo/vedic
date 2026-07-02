import { Navigate, Route, Routes } from "react-router-dom";
import { Landing } from "./screens/Landing";
import { Intake } from "./screens/Intake";
import { Session } from "./screens/Session";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/new" element={<Intake />} />
      <Route path="/session/:id" element={<Session />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
