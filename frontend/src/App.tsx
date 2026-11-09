// Routes. Everything except /login needs a logged-in user.

import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ToastProvider } from "./components/Toast";
import { Skeleton } from "./components/ui";
import { AuthProvider, useAuth } from "./lib/auth";
import Disputes from "./pages/Disputes";
import Guardian from "./pages/Guardian";
import Home from "./pages/Home";
import Login from "./pages/Login";
import Notifications from "./pages/Notifications";
import Pay from "./pages/Pay";
import PaymentDetail from "./pages/PaymentDetail";

function RequireLogin() {
  const { me, ready } = useAuth();
  if (!ready) {
    return (
      <div className="mx-auto max-w-md space-y-4 p-6">
        <Skeleton className="h-10 w-40" />
        <Skeleton className="h-44" />
        <Skeleton className="h-24" />
      </div>
    );
  }
  return me ? <AppShell /> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<RequireLogin />}>
              <Route index element={<Home />} />
              <Route path="pay" element={<Pay />} />
              <Route path="payments/:id" element={<PaymentDetail />} />
              <Route path="disputes" element={<Disputes />} />
              <Route path="guardian" element={<Guardian />} />
              <Route path="notifications" element={<Notifications />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </AuthProvider>
  );
}
