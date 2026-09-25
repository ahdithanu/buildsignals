import { lazy, Suspense } from 'react';
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/contexts/AuthContext";
import { SessionQueryProvider } from "@/components/auth/SessionQueryProvider";
import {
  RedirectIfAuthenticated,
  RequireAuth,
} from "@/components/auth/RequireAuth";
import { ErrorBoundary } from "@/components/ErrorBoundary";

const Dashboard = lazy(() => import('./pages/Dashboard'));
const DealInbox = lazy(() => import('./pages/DealInbox'));
const DealDetail = lazy(() => import('./pages/DealDetail'));
const Underwriting = lazy(() => import('./pages/Underwriting'));
const MemoGenerator = lazy(() => import('./pages/MemoGenerator'));
const Pipeline = lazy(() => import('./pages/Pipeline'));
const MarketSignals = lazy(() => import('./pages/MarketSignals'));
const PermitBrandReview = lazy(() => import('./pages/PermitBrandReview'));
const BrandExpansion = lazy(() => import('./pages/BrandExpansion'));
const PlanningSignals = lazy(() => import('./pages/PlanningSignals'));
const PermitDetail = lazy(() => import('./pages/PermitDetail'));
const IngestionOperations = lazy(() => import('./pages/IngestionOperations'));
const IngestionCandidateDetail = lazy(() => import('./pages/IngestionCandidateDetail'));
const IngestionSourceDetail = lazy(() => import('./pages/IngestionSourceDetail'));
const GraphEntityDetail = lazy(() => import('./pages/GraphEntityDetail'));
const GraphRelationshipDetail = lazy(() => import('./pages/GraphRelationshipDetail'));
const GraphExplorer = lazy(() => import('./pages/GraphExplorer'));
const GraphVerificationQueue = lazy(() => import('./pages/GraphVerificationQueue'));
const ParcelDetail = lazy(() => import('./pages/ParcelDetail'));
const AcquisitionRadar = lazy(() => import('./pages/AcquisitionRadar'));
const AcquisitionMap = lazy(() => import('./pages/AcquisitionMap'));
const Settings = lazy(() => import('./pages/Settings'));
const AuditLog = lazy(() => import('./pages/AuditLog'));
const Team = lazy(() => import('./pages/Team'));
const Account = lazy(() => import('./pages/Account'));
const Login = lazy(() => import('./pages/Login'));
const Register = lazy(() => import('./pages/Register'));
const ForgotPassword = lazy(() => import('./pages/ForgotPassword'));
const ResetPassword = lazy(() => import('./pages/ResetPassword'));
const NotFound = lazy(() => import('./pages/NotFound'));

const App = () => (
  <AuthProvider>
    <SessionQueryProvider>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <ErrorBoundary>
          <Suspense fallback={<main role="status" className="flex min-h-dvh items-center justify-center p-6 text-sm text-muted-foreground">Loading...</main>}>
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
            <Route
              path="/forgot-password"
              element={
                <RedirectIfAuthenticated>
                  <ForgotPassword />
                </RedirectIfAuthenticated>
              }
            />
            <Route
              path="/reset-password"
              element={
                <RedirectIfAuthenticated>
                  <ResetPassword />
                </RedirectIfAuthenticated>
              }
            />

            {/* Authenticated routes */}
            <Route path="/admin/evals" element={<RequireAuth><Evaluations /></RequireAuth>} />
            <Route path="/admin/observability" element={<RequireAuth><Observability /></RequireAuth>} />
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
              path="/map"
              element={
                <RequireAuth>
                  <AcquisitionMap />
                </RequireAuth>
              }
            />
            <Route
              path="/brand-expansion"
              element={
                <RequireAuth>
                  <BrandExpansion />
                </RequireAuth>
              }
            />
            <Route
              path="/planning"
              element={
                <RequireAuth>
                  <PlanningSignals />
                </RequireAuth>
              }
            />
            <Route
              path="/permit-review"
              element={
                <RequireAuth>
                  <PermitBrandReview />
                </RequireAuth>
              }
            />
            <Route
              path="/permits/:permitId"
              element={
                <RequireAuth>
                  <PermitDetail />
                </RequireAuth>
              }
            />
            <Route
              path="/source-health"
              element={
                <RequireAuth>
                  <IngestionOperations />
                </RequireAuth>
              }
            />
            <Route
              path="/source-health/sources/:sourceId"
              element={
                <RequireAuth>
                  <IngestionSourceDetail />
                </RequireAuth>
              }
            />
            <Route
              path="/source-health/candidates/:candidateKey"
              element={
                <RequireAuth>
                  <IngestionCandidateDetail />
                </RequireAuth>
              }
            />
            <Route
              path="/graph/entities/:entityId"
              element={
                <RequireAuth>
                  <GraphEntityDetail />
                </RequireAuth>
              }
            />
            <Route
              path="/graph/relationships/:relationshipId"
              element={
                <RequireAuth>
                  <GraphRelationshipDetail />
                </RequireAuth>
              }
            />
            <Route
              path="/graph"
              element={
                <RequireAuth>
                  <GraphExplorer />
                </RequireAuth>
              }
            />
            <Route
              path="/graph/verification"
              element={
                <RequireAuth>
                  <GraphVerificationQueue />
                </RequireAuth>
              }
            />
            <Route
              path="/acquisition-radar"
              element={
                <RequireAuth>
                  <AcquisitionRadar />
                </RequireAuth>
              }
            />
            <Route
              path="/parcels/:parcelId"
              element={
                <RequireAuth>
                  <ParcelDetail />
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
            <Route
              path="/account"
              element={
                <RequireAuth>
                  <Account />
                </RequireAuth>
              }
            />
            <Route path="*" element={<NotFound />} />
          </Routes>
          </Suspense>
          </ErrorBoundary>
        </BrowserRouter>
      </TooltipProvider>
    </SessionQueryProvider>
  </AuthProvider>
);

export default App;
