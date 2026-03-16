import { Routes, Route, Navigate } from "react-router-dom";
import { Spinner, Text } from "@fluentui/react-components";
import { useAuth } from "./auth/AuthProvider";
import { useTeams } from "./context/TeamsProvider";

// Student pages
import StudentDashboard from "./pages/student/StudentDashboard";
import TestBuilderPage from "./pages/student/TestBuilderPage";
import TestHistoryPage from "./pages/student/TestHistoryPage";
import AppointmentsPage from "./pages/student/AppointmentsPage";

// Teacher pages
import TeacherClassList from "./pages/teacher/TeacherClassList";
import ClassDetailPage from "./pages/teacher/ClassDetailPage";
import StudentDetailPage from "./pages/teacher/StudentDetailPage";
import TeacherTestsPage from "./pages/teacher/TeacherTestsPage";

function LoginPage() {
  const { login } = useAuth();
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", marginTop: 80, gap: 16 }}>
      <Text size={600} weight="semibold">Kompetenz-Dashboard</Text>
      <Text>Bitte melde dich mit deinem Schulkonto an.</Text>
      <button onClick={login} style={{ padding: "10px 24px", fontSize: 16, cursor: "pointer" }}>
        Mit Microsoft anmelden
      </button>
    </div>
  );
}

export default function App() {
  const { user, loading } = useAuth();
  const { inTeams } = useTeams();

  if (loading) {
    return <Spinner label="Laden..." style={{ marginTop: 80 }} />;
  }

  if (!user) {
    return <LoginPage />;
  }

  if (user.is_teacher) {
    return (
      <Routes>
        <Route path="/" element={<Navigate to="/teacher/classes" replace />} />
        <Route path="/teacher/classes" element={<TeacherClassList />} />
        <Route path="/teacher/classes/:classId" element={<ClassDetailPage />} />
        <Route path="/teacher/classes/:classId/students/:studentId" element={<StudentDetailPage />} />
        <Route path="/teacher/classes/:classId/tests" element={<TeacherTestsPage />} />
        <Route path="*" element={<Navigate to="/teacher/classes" replace />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route path="/" element={<Navigate to="/student/dashboard" replace />} />
      <Route path="/student/dashboard" element={<StudentDashboard />} />
      <Route path="/student/test-builder" element={<TestBuilderPage />} />
      <Route path="/student/tests" element={<TestHistoryPage />} />
      <Route path="/student/appointments" element={<AppointmentsPage />} />
      <Route path="*" element={<Navigate to="/student/dashboard" replace />} />
    </Routes>
  );
}
