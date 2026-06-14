import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  ArcElement,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from "chart.js";
import { Bar, Line, Pie } from "react-chartjs-2";

ChartJS.register(
  ArcElement,
  BarElement,
  CategoryScale,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
  Legend,
  Filler
);

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function SummaryCard({ label, value, tone = "green" }) {
  const toneClass = tone === "red" ? "text-red-400" : "text-green-400";

  return (
    <div className="rounded-2xl border border-green-400/20 bg-gray-900/60 p-5 shadow-xl shadow-green-500/5">
      <p className="text-xs uppercase tracking-[0.25em] text-gray-500">{label}</p>
      <p className={`mt-3 text-2xl font-black ${toneClass}`}>{value}</p>
    </div>
  );
}

function ChartPanel({ title, children }) {
  return (
    <div className="rounded-2xl border border-gray-800 bg-gray-900/60 p-5 shadow-2xl shadow-black/20">
      <h2 className="mb-4 text-lg font-black text-white">{title}</h2>
      <div className="h-[320px]">{children}</div>
    </div>
  );
}

export default function Analytics({ addToast }) {
  const [stats, setStats] = useState(null);
  const [violations, setViolations] = useState([]);

  const fetchAnalytics = async () => {
    try {
      const [statsResponse, violationsResponse] = await Promise.all([
        axios.get(`${API_BASE}/stats`),
        axios.get(`${API_BASE}/violations`),
      ]);

      setStats(statsResponse.data);
      setViolations(violationsResponse.data || []);
    } catch {
      addToast?.({
        type: "danger",
        title: "Analytics unavailable",
        message: "Unable to fetch dashboard data.",
      });
    }
  };

  useEffect(() => {
    fetchAnalytics();
  }, []);

  const byType = stats?.by_type || {};

  const typeLabels = Object.keys(byType);
  const typeValues = Object.values(byType);

  const hourlyCounts = useMemo(() => {
    const hours = Array.from({ length: 24 }, () => 0);

    violations.forEach((record) => {
      const date = new Date(record.timestamp);
      const hour = Number.isNaN(date.getHours()) ? null : date.getHours();

      if (hour !== null) {
        hours[hour] += 1;
      }
    });

    return hours;
  }, [violations]);

  const dailyRevenue = useMemo(() => {
    const days = [];

    for (let i = 13; i >= 0; i -= 1) {
      const date = new Date();
      date.setDate(date.getDate() - i);

      days.push({
        key: date.toISOString().slice(0, 10),
        label: date.toLocaleDateString("en-IN", {
          day: "2-digit",
          month: "short",
        }),
        value: 0,
      });
    }

    violations.forEach((record) => {
      const key = String(record.timestamp || "").slice(0, 10);
      const day = days.find((item) => item.key === key);

      if (day) {
        day.value += Number(record.fine_amount || 0);
      }
    });

    return days;
  }, [violations]);

  const mostCommonViolation = useMemo(() => {
    if (typeLabels.length === 0) return "N/A";

    return typeLabels.reduce((best, current) =>
      byType[current] > byType[best] ? current : best
    );
  }, [byType, typeLabels]);

  const busiestHour = useMemo(() => {
    const max = Math.max(...hourlyCounts);

    if (max === 0) return "N/A";

    return `${hourlyCounts.indexOf(max)}:00`;
  }, [hourlyCounts]);

  const totalFines = violations.reduce(
    (sum, item) => sum + Number(item.fine_amount || 0),
    0
  );

  const chartBaseOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        labels: {
          color: "#d1d5db",
        },
      },
      tooltip: {
        backgroundColor: "#030712",
        titleColor: "#4ade80",
        bodyColor: "#ffffff",
        borderColor: "rgba(74,222,128,0.25)",
        borderWidth: 1,
      },
    },
    scales: {
      x: {
        ticks: { color: "#9ca3af" },
        grid: { color: "rgba(75,85,99,0.25)" },
      },
      y: {
        ticks: { color: "#9ca3af" },
        grid: { color: "rgba(75,85,99,0.25)" },
      },
    },
  };

  const pieData = {
    labels: typeLabels.length ? typeLabels : ["No Data"],
    datasets: [
      {
        data: typeValues.length ? typeValues : [1],
        backgroundColor: [
          "#4ade80",
          "#ef4444",
          "#facc15",
          "#38bdf8",
          "#a855f7",
          "#fb923c",
        ],
        borderColor: "#030712",
        borderWidth: 2,
      },
    ],
  };

  const hourlyData = {
    labels: Array.from({ length: 24 }, (_, index) => `${index}:00`),
    datasets: [
      {
        label: "Violations",
        data: hourlyCounts,
        backgroundColor: "rgba(74,222,128,0.65)",
        borderColor: "#4ade80",
        borderWidth: 1,
      },
    ],
  };

  const revenueData = {
    labels: dailyRevenue.map((item) => item.label),
    datasets: [
      {
        label: "Fine Revenue",
        data: dailyRevenue.map((item) => item.value),
        borderColor: "#4ade80",
        backgroundColor: "rgba(74,222,128,0.12)",
        tension: 0.35,
        fill: true,
      },
    ],
  };

  const topOffenders = stats?.top_offenders || [];

  const offendersData = {
    labels: topOffenders.map((item) => item.plate),
    datasets: [
      {
        label: "Violation Count",
        data: topOffenders.map((item) => item.count),
        backgroundColor: "rgba(239,68,68,0.7)",
        borderColor: "#ef4444",
        borderWidth: 1,
      },
    ],
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Analytics Command Center</h1>
        <p className="text-sm text-gray-500">
          Violation patterns, revenue trends, and repeat offender intelligence.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <SummaryCard
          label="Total Violations"
          value={stats?.total_violations ?? 0}
        />
        <SummaryCard label="Total Fines" value={`₹${totalFines}`} tone="red" />
        <SummaryCard label="Most Common" value={mostCommonViolation} />
        <SummaryCard label="Busiest Hour" value={busiestHour} tone="red" />
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <ChartPanel title="Violations by Type">
          <Pie
            data={pieData}
            options={{
              responsive: true,
              maintainAspectRatio: false,
              plugins: chartBaseOptions.plugins,
            }}
          />
        </ChartPanel>

        <ChartPanel title="Violations by Hour of Day">
          <Bar data={hourlyData} options={chartBaseOptions} />
        </ChartPanel>

        <ChartPanel title="Daily Fine Revenue - Last 14 Days">
          <Line data={revenueData} options={chartBaseOptions} />
        </ChartPanel>

        <ChartPanel title="Top 10 Repeat Offenders">
          <Bar
            data={offendersData}
            options={{
              ...chartBaseOptions,
              indexAxis: "y",
            }}
          />
        </ChartPanel>
      </div>
    </div>
  );
}