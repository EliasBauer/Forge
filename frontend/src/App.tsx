import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./contexts/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import LoginPage from "./pages/LoginPage";
import AufgabenPage from "./pages/AufgabenPage";
import ProjektListePage from "./pages/ProjektListePage";
import ProjektDetailPage from "./pages/ProjektDetailPage";
import ProjektNeuPage from "./pages/ProjektNeuPage";
import StundensaetzePage from "./pages/StundensaetzePage";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Navigate to="/projekte" replace />
              </ProtectedRoute>
            }
          />
          <Route
            path="/aufgaben"
            element={
              <ProtectedRoute>
                <AufgabenPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/projekte"
            element={
              <ProtectedRoute>
                <ProjektListePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/projekte/neu"
            element={
              <ProtectedRoute allowedGroups={["Admin", "Projektleiter"]}>
                <ProjektNeuPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/projekte/:id"
            element={
              <ProtectedRoute>
                <ProjektDetailPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/stundensaetze"
            element={
              <ProtectedRoute allowedGroups={["Admin", "Projektleiter"]}>
                <StundensaetzePage />
              </ProtectedRoute>
            }
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
