import React, { useEffect, useMemo, useState } from "react";
import {
  BrowserRouter,
  NavLink,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";

import LiveMonitor from "./pages/LiveMonitor";
import ViolationsLog from "./pages/ViolationsLog";
import Analytics from "./pages/Analytics";
import DisputePortal from "./pages/DisputePortal";

const navItems = [
  {
    path: "/live",
    label: "Live Monitor",
    icon: "📡",
  },
  {
    path: "/violations",
    label: "Violations Log",
    icon: "📜",
  },
  {
    path: "/analytics",
    label: "Analytics",
    icon: "📊",
  },
  {
    path: "/dispute",
    label: "Dispute Portal",
    icon: "⚖️",
  },
];

function ToastContainer({ toasts, removeToast }) {
  return (
    <div className="fixed right-5 top-5 z-[999] w-full max-w-sm space-y-3">
      {toasts.map((toast) => {
        const isDanger = toast.type === "danger";

        return (
          <div
            key={toast.id}
            className={`rounded-xl border p-4 shadow-2xl backdrop-blur ${
              isDanger
                ? "border-red-500/30 bg-red-950/80 shadow-red-500/10"
                : "border-green-400/30 bg-green-950/80 shadow-green-400/10"
            }`}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3
                  className={`font-black ${
                    isDanger ? "text-red-400" : "text-green-400"
                  }`}
                >
                  {toast.title}
                </h3>
                <p className="mt-1 text-sm text-gray-300">{toast.message}</p>
              </div>

              <button
                onClick={() => removeToast(toast.id)}
                className="text-gray-500 transition hover:text-white"
              >
                ✕
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 z-40 hidden h-screen w-72 border-r border-green-400/10 bg-gray-950/95 p-5 shadow-2xl shadow-black/30 backdrop-blur lg:block">
      <div className="mb-10 rounded-2xl border border-green-400/20 bg-green-400/5 p-5">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-green-400/30 bg-green-400/10 text-2xl">
            🚦
          </div>

          <div>
            <h1 className="text-xl font-black tracking-tight text-white">
              AutoSentinel
            </h1>
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-green-400">
              AI Traffic Enforcement
            </p>
          </div>
        </div>
      </div>

      <nav className="space-y-2">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-bold transition ${
                isActive
                  ? "border border-green-400/30 bg-green-400/10 text-green-400 shadow-lg shadow-green-400/5"
                  : "text-gray-400 hover:bg-gray-900 hover:text-white"
              }`
            }
          >
            <span className="text-lg">{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="absolute bottom-5 left-5 right-5 rounded-2xl border border-red-500/20 bg-red-950/20 p-4">
        <p className="text-xs font-black uppercase tracking-[0.2em] text-red-400">
          Surveillance Mode
        </p>
        <p className="mt-2 text-sm leading-6 text-gray-400">
          Real-time monitoring, OCR, detection, challan generation, and dispute
          workflow.
        </p>
      </div>
    </aside>
  );
}

function MobileTopbar() {
  return (
    <div className="sticky top-0 z-30 border-b border-green-400/10 bg-gray-950/95 p-4 backdrop-blur lg:hidden">
      <div className="mb-4 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-green-400/30 bg-green-400/10 text-xl">
          🚦
        </div>
        <div>
          <h1 className="font-black text-white">AutoSentinel</h1>
          <p className="text-xs uppercase tracking-[0.2em] text-green-400">
            AI Traffic Enforcement
          </p>
        </div>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `whitespace-nowrap rounded-lg px-3 py-2 text-xs font-bold ${
                isActive
                  ? "bg-green-400 text-gray-950"
                  : "bg-gray-900 text-gray-400"
              }`
            }
          >
            {item.icon} {item.label}
          </NavLink>
        ))}
      </div>
    </div>
  );
}

function AppShell() {
  const [toasts, setToasts] = useState([]);

  const addToast = ({ type = "success", title, message }) => {
    const id = crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random()}`;

    setToasts((prev) => [
      {
        id,
        type,
        title,
        message,
      },
      ...prev,
    ]);

    setTimeout(() => {
      setToasts((prev) => prev.filter((toast) => toast.id !== id));
    }, 4500);
  };

  const removeToast = (id) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  };

  const pageProps = useMemo(
    () => ({
      addToast,
    }),
    []
  );

  useEffect(() => {
    document.body.classList.add("bg-gray-950");

    return () => {
      document.body.classList.remove("bg-gray-950");
    };
  }, []);

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_top_right,_rgba(74,222,128,0.12),_transparent_35%),radial-gradient(circle_at_bottom_left,_rgba(239,68,68,0.10),_transparent_30%)]" />
      <div className="pointer-events-none fixed inset-0 opacity-[0.04] [background-image:linear-gradient(#fff_1px,transparent_1px),linear-gradient(90deg,#fff_1px,transparent_1px)] [background-size:40px_40px]" />

      <Sidebar />
      <MobileTopbar />

      <main className="relative z-10 px-4 py-6 lg:ml-72 lg:px-8">
        <Routes>
          <Route path="/" element={<Navigate to="/live" replace />} />
          <Route path="/live" element={<LiveMonitor {...pageProps} />} />
          <Route path="/violations" element={<ViolationsLog {...pageProps} />} />
          <Route path="/analytics" element={<Analytics {...pageProps} />} />
          <Route path="/dispute" element={<DisputePortal {...pageProps} />} />
        </Routes>
      </main>

      <ToastContainer toasts={toasts} removeToast={removeToast} />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppShell />
    </BrowserRouter>
  );
}