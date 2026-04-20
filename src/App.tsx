import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/contexts/AuthContext";
import Dashboard from "./pages/Dashboard";
import DealInbox from "./pages/DealInbox";
import DealDetail from "./pages/DealDetail";
import Underwriting from "./pages/Underwriting";
import MemoGenerator from "./pages/MemoGenerator";
import Pipeline from "./pages/Pipeline";
import MarketSignals from "./pages/MarketSignals";
import Settings from "./pages/Settings";
import Login from "./pages/Login";
import Register from "./pages/Register";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <AuthProvider>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/" element={<Dashboard />} />
            <Route path="/inbox" element={<DealInbox />} />
            <Route path="/deal/:id" element={<DealDetail />} />
            <Route path="/underwriting" element={<Underwriting />} />
            <Route path="/memo" element={<MemoGenerator />} />
            <Route path="/pipeline" element={<Pipeline />} />
            <Route path="/signals" element={<MarketSignals />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </TooltipProvider>
    </AuthProvider>
  </QueryClientProvider>
);

export default App;
