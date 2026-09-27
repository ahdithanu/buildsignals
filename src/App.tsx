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
import Dashboard from "./pages/Dashboard";
import DealInbox from "./pages/DealInbox";
import DealDetail from "./pages/DealDetail";
import Underwriting from "./pages/Underwriting";
import MemoGenerator from "./pages/MemoGenerator";
import Pipeline from "./pages/Pipeline";
import MarketSignals from "./pages/MarketSignals";
import PermitBrandReview from "./pages/PermitBrandReview";
import BrandExpansion from "./pages/BrandExpansion";
import PlanningSignals from "./pages/PlanningSignals";
import PermitDetail from "./pages/PermitDetail";
import IngestionOperations from "./pages/IngestionOperations";
import IngestionCandidateDetail from "./pages/IngestionCandidateDetail";
import IngestionSourceDetail from "./pages/IngestionSourceDetail";
import GraphEntityDetail from "./pages/GraphEntityDetail";
import GraphRelationshipDetail from "./pages/GraphRelationshipDetail";
import GraphExplorer from "./pages/GraphExplorer";
import GraphVerificationQueue from "./pages/GraphVerificationQueue";
import ParcelDetail from "./pages/ParcelDetail";
import AcquisitionRadar from "./pages/AcquisitionRadar";
import AcquisitionMap from "./pages/AcquisitionMap";
import Settings from "./pages/Settings";
import AuditLog from "./pages/AuditLog";
import Evaluations from "./pages/Evaluations";
import PromptRegistry from "./pages/PromptRegistry";
import Team from "./pages/Team";
import Account from "./pages/Account";
import Login from "./pages/Login";
import Register from "./pages/Register";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import NotFound from "./pages/NotFound";
import { ErrorBoundary } from "@/components/ErrorBoundary";

const App = () => (
  <AuthProvider>
    <SessionQueryProvider>
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
            <Route path="/admin/prompts" element={<RequireAuth><PromptRegistry /></RequireAuth>} />
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
          </ErrorBoundary>
        </BrowserRouter>
      </TooltipProvider>
    </SessionQueryProvider>
  </AuthProvider>
);

export default App;
