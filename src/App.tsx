import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/contexts/AuthContext";
import {
  RedirectIfAuthenticated,
  RequireAuth,
} from "@/components/auth/RequireAuth";
import Dashboard from "./pages/Dashboard";
import DealInbox from "./pages/DealInbox";
import DealDetail from "./pages/DealDetail";
import Underwriting from "./pages/Underwriting";
import MemoGenerator from "./pages/MemoGenerator";
import Pipeline from "./pages/Pipeline";
import MarketSignals from "./pages/MarketSignals";
import Settings from "./pages/Settings";
import AuditLog from "./pages/AuditLog";
import Team from "./pages/Team";
import Login from "./pages/Login";
import Register from "./pages/Register";
import NotFound from "./pages/NotFound";
import { ErrorBoundary } from "@/components/ErrorBoundary";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <AuthProvider>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <ErrorBoundary>
          <Routes>
            {/* Public — authed users get bounced back to the app */}
            <Route
              path="/login"
              element={
                <RedirectIfAuthenticated>
                  <Login />
                </RedirectIfAuthenticated>
              }
            />
            <Route
              path="/register"
              element={
                <RedirectIfAuthenticated>
                  <Register />
                </RedirectIfAuthenticated>
              }
            />

            {/* Authenticated routes */}
            <Route
              path="/"
              element={
                <RequireAuth>
                  <Dashboard />
                </RequireAuth>
              }
            />
            <Route
              path="/inbox"
              element={
                <RequireAuth>
                  <DealInbox />
                </RequireAuth>
              }
            />
            <Route
              path="/deal/:id"
              element={
                <RequireAuth>
                  <DealDetail />
                </RequireAuth>
              }
            />
            <Route
              path="/underwriting"
              element={
                <RequireAuth>
                  <Underwriting />
                </RequireAuth>
              }
            />
            <Route
              path="/memo"
              element={
                <RequireAuth>
                  <MemoGenerator />
                </RequireAuth>
              }
            />
            <Route
              path="/pipeline"
              element={
                <RequireAuth>
                  <Pipeline />
                </RequireAuth>
              }
            />
            <Route
              path="/signals"
              element={
                <RequireAuth>
                  <MarketSignals />
                </RequireAuth>
              }
            />
            <Route
              path="/settings"
              element={
                <RequireAuth>
                  <Settings />
                </RequireAuth>
              }
            />
            <Route
              path="/audit"
              element={
                <RequireAuth>
                  <AuditLog />
                </RequireAuth>
              }
            />
            <Route
              path="/team"
              element={
                <RequireAuth>
                  <Team />
                </RequireAuth>
              }
            />
            <Route path="*" element={<NotFound />} />
          </Routes>
          </ErrorBoundary>
        </BrowserRouter>
      </TooltipProvider>
    </AuthProvider>
  </QueryClientProvider>
);

export default App;
