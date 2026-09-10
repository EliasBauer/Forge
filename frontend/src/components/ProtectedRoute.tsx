import { Navigate } from "react-router-dom";
import { useAuth, type AuthCapabilities } from "../contexts/AuthContext";

type Props = {
  children: React.ReactNode;
  requiredCapability?: keyof AuthCapabilities;
};

export default function ProtectedRoute({ children, requiredCapability }: Props) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <p className="text-gray-400">Lade…</p>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (requiredCapability && !user.capabilities[requiredCapability]) {
    return <Navigate to="/projekte" replace />;
  }

  return <>{children}</>;
}
