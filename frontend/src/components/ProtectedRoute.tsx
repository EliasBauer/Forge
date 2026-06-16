import { Navigate } from "react-router-dom";
import { useAuth, type UserGroup } from "../contexts/AuthContext";

type Props = {
  children: React.ReactNode;
  allowedGroups?: UserGroup[];
};

export default function ProtectedRoute({ children, allowedGroups }: Props) {
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

  if (allowedGroups && !allowedGroups.some((g) => user.groups.includes(g))) {
    return <Navigate to="/projekte" replace />;
  }

  return <>{children}</>;
}
