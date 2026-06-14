import React, { useEffect, useRef, useState } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const WS_BASE = API_BASE.replace(/^http/, "ws");

const violationIcons = {
  seatbelt: "🎗️",
  phone: "📱",
  speed: "⚡",
  helmet: "🪖",
  wrong_way: "↩️",
  drowsiness: "😴",
};

function StatCard({ label, value, accent = "text-green-400" }) {
  return (
    <div className="rounded-xl border border-green-400/20 bg-gray-900/70 p-4 shadow-lg shadow-green-500/5">
      <p className="text-xs uppercase tracking-[0.25em] text-gray-500">{label}</p>
      <p className={`mt-2 text-2xl font-black ${accent}`}>{value}</p>
    </div>
  );
}

function AlertCard({ alert }) {
  const firstType = Array.isArray(alert.violations)
    ? alert.violations[0]
    : alert.violation_type || "violation";

  return (
    <div className="animate-[slideDown_0.35s_ease-out] rounded-xl border border-red-500/30 bg-red-950/30 p-4 shadow-lg shadow-red-500/10">
      <div className="flex items-start gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-lg border border-red-500/40 bg-red-500/10 text-xl">
          {violationIcons[firstType] || "🚨"}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <h3 className="truncate text-sm font-bold uppercase tracking-wider text-red-400">
              {Array.isArray(alert.violations)
                ? alert.violations.join(", ")
                : alert.violation_type || "Violation"}
            </h3>
            <span className="rounded-full bg-red-500/10 px-2 py-1 text-xs font-bold text-red-400">
              LIVE
            </span>
          </div>

          <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
            <p className="text-gray-400">
              Plate: <span className="font-bold text-white">{alert.plate}</span>
            </p>
            <p className="text-gray-400">
              Fine:{" "}
              <span className="font-bold text-red-400">
                ₹{alert.fine_total || alert.fine_amount || 0}
              </span>
            </p>
            <p className="col-span-2 text-xs text-gray-500">
              {alert.timestamp || new Date().toLocaleString()}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function LiveMonitor({ addToast }) {
  const [feedUrl, setFeedUrl] = useState("");
  const [alerts, setAlerts] = useState([]);
  const [totalToday, setTotalToday] = useState(0);
  const [finesToday, setFinesToday] = useState(0);
  const [connectionStatus, setConnectionStatus] = useState("CONNECTING");
  const latestObjectUrl = useRef(null);

  const fetchTodayStats = async () => {
    try {
      const response = await axios.get(`${API_BASE}/violations`);
      const today = new Date().toISOString().slice(0, 10);

      const todayRecords = response.data.filter((item) =>
        String(item.timestamp || "").startsWith(today)
      );

      setTotalToday(todayRecords.length);
      setFinesToday(
        todayRecords.reduce((sum, item) => sum + Number(item.fine_amount || 0), 0)
      );
    } catch {
      setTotalToday(alerts.length);
      setFinesToday(
        alerts.reduce(
          (sum, item) => sum + Number(item.fine_total || item.fine_amount || 0),
          0
        )
      );
    }
  };

  useEffect(() => {
    fetchTodayStats();

    const ws = new WebSocket(`${WS_BASE}/live-feed`);

    ws.onopen = () => setConnectionStatus("LIVE");
    ws.onerror = () => setConnectionStatus("OFFLINE");
    ws.onclose = () => setConnectionStatus("DISCONNECTED");

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        // 1. Paint the video frame
        if (data.image) {
          setFeedUrl(`data:image/jpeg;base64,${data.image}`);
        }
        
        // 2. If the AI sent a ticket, pop it onto the screen!
        if (data.alert) {
          setAlerts((prev) => [data.alert, ...prev].slice(0, 20));
          setTotalToday((prev) => prev + 1);
          setFinesToday((prev) => prev + Number(data.alert.fine_total || 0));
        }
      } catch (err) {
        // Fallback for raw text
        setFeedUrl(`data:image/jpeg;base64,${event.data}`);
      }
    };

    return () => {
      ws.close();

      if (latestObjectUrl.current) {
        URL.revokeObjectURL(latestObjectUrl.current);
      }
    };
  }, []);

  const simulateViolation = async () => {
    try {
      const response = await axios.get(`${API_BASE}/simulate-violation`);
      const data = response.data;

      const alert = {
        ...data,
        timestamp: new Date().toLocaleString(),
      };

      setAlerts((prev) => [alert, ...prev].slice(0, 20));
      setTotalToday((prev) => prev + 1);
      setFinesToday((prev) => prev + Number(data.fine_total || 0));

      addToast?.({
        type: "danger",
        title: "New violation detected",
        message: `${data.plate} • ₹${data.fine_total}`,
      });
    } catch {
      addToast?.({
        type: "danger",
        title: "Simulation failed",
        message: "Backend is not reachable.",
      });
    }
  };

  return (
    <div className="space-y-6">
      <style>
        {`
          @keyframes slideDown {
            from { opacity: 0; transform: translateY(-18px); }
            to { opacity: 1; transform: translateY(0); }
          }
        `}
      </style>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <StatCard label="Total Today" value={totalToday} />
        <StatCard label="Fines Today" value={`₹${finesToday}`} accent="text-red-400" />
        <StatCard label="Feed Status" value={connectionStatus} />
        <StatCard label="Camera Unit" value="CAM-DL-001" />
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.7fr_1fr]">
        <section className="rounded-2xl border border-green-400/20 bg-gray-900/60 p-4 shadow-2xl shadow-green-500/5">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h1 className="text-xl font-black text-white">Live Surveillance Feed</h1>
              <p className="text-sm text-gray-500">
                Computer vision stream with real-time violation overlays
              </p>
            </div>

            <div className="flex items-center gap-2 rounded-full border border-green-400/30 bg-green-400/10 px-3 py-1 text-xs font-bold text-green-400">
              <span className="h-2 w-2 animate-pulse rounded-full bg-green-400" />
              MONITORING
            </div>
          </div>

          <div className="relative aspect-video overflow-hidden rounded-xl border border-gray-800 bg-black">
            {feedUrl ? (
              <img
                src={feedUrl}
                alt="AutoSentinel live feed"
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center bg-[radial-gradient(circle_at_center,_rgba(74,222,128,0.12),_transparent_55%)]">
                <div className="text-center">
                  <div className="mx-auto mb-4 h-16 w-16 animate-pulse rounded-full border border-green-400/40 bg-green-400/10" />
                  <p className="font-mono text-green-400">WAITING FOR LIVE FEED...</p>
                  <p className="mt-2 text-sm text-gray-500">
                    WebSocket: {WS_BASE}/live-feed
                  </p>
                </div>
              </div>
            )}

            <div className="absolute left-4 top-4 rounded-lg bg-black/70 px-3 py-2 font-mono text-xs text-green-400 backdrop-blur">
              REC ● 1080P / AI SCAN ACTIVE
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-red-500/20 bg-gray-900/60 p-4 shadow-2xl shadow-red-500/5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-black text-white">Real-Time Alerts</h2>
              <p className="text-sm text-gray-500">Latest enforcement events</p>
            </div>

            <button
              onClick={simulateViolation}
              className="rounded-lg bg-red-500 px-4 py-2 text-xs font-black uppercase tracking-wider text-white shadow-lg shadow-red-500/20 transition hover:bg-red-400"
            >
              Simulate Violation
            </button>
          </div>

          <div className="max-h-[560px] space-y-3 overflow-y-auto pr-1">
            {alerts.length === 0 ? (
              <div className="rounded-xl border border-gray-800 bg-gray-950/80 p-8 text-center">
                <p className="font-mono text-sm text-gray-500">
                  NO ACTIVE ALERTS
                </p>
                <p className="mt-2 text-xs text-gray-600">
                  Press simulate to test dashboard flow.
                </p>
              </div>
            ) : (
              alerts.map((alert, index) => (
                <AlertCard
                  key={`${alert.case_id || alert.plate}-${index}`}
                  alert={alert}
                />
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  );
}