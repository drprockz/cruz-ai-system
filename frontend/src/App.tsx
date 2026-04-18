import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Layout } from "./components/Layout";
import { lazy, Suspense } from "react";

const ConversationTab = lazy(() =>
  import("./tabs/ConversationTab").then((m) => ({ default: m.ConversationTab })),
);
const DashboardTab = lazy(() =>
  import("./tabs/DashboardTab").then((m) => ({ default: m.DashboardTab })),
);
const EventsTab = lazy(() =>
  import("./tabs/EventsTab").then((m) => ({ default: m.EventsTab })),
);
const ApprovalsTab = lazy(() =>
  import("./tabs/ApprovalsTab").then((m) => ({ default: m.ApprovalsTab })),
);
// VoiceMode is a full-screen takeover — rendered outside <Layout>.
const VoiceMode = lazy(() => import("./routes/VoiceMode"));

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 5_000 } } });

function TabbedShell() {
  return (
    <Layout>
      <Suspense fallback={<div className="p-6 text-zinc-500">Loading…</div>}>
        <Routes>
          <Route path="/" element={<Navigate to="/tab/conversation" replace />} />
          <Route path="/tab/conversation" element={<ConversationTab />} />
          <Route path="/tab/dashboard" element={<DashboardTab />} />
          <Route path="/tab/events" element={<EventsTab />} />
          <Route path="/tab/approvals" element={<ApprovalsTab />} />
          <Route path="/tab/approvals/:id" element={<ApprovalsTab />} />
        </Routes>
      </Suspense>
    </Layout>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Suspense fallback={<div className="p-6 text-zinc-500">Loading…</div>}>
          <Routes>
            <Route path="/voice" element={<VoiceMode />} />
            <Route path="/*" element={<TabbedShell />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
