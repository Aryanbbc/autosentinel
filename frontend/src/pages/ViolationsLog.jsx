import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const statusStyles = {
  unpaid: "bg-red-500/10 text-red-400 border-red-500/30",
  paid: "bg-green-500/10 text-green-400 border-green-500/30",
  disputed: "bg-yellow-500/10 text-yellow-300 border-yellow-500/30",
};

function resolveEvidenceUrl(path) {
  if (!path) return "";

  if (path.startsWith("http")) return path;

  const normalized = path.replaceAll("\\", "/");
  const evidenceIndex = normalized.indexOf("evidence/");

  if (evidenceIndex !== -1) {
    return `${API_BASE}/${normalized.slice(evidenceIndex)}`;
  }

  return `${API_BASE}/${normalized}`;
}

export default function ViolationsLog({ addToast }) {
  const [violations, setViolations] = useState([]);
  const [date, setDate] = useState("");
  const [type, setType] = useState("");
  const [plate, setPlate] = useState("");
  const [page, setPage] = useState(1);
  const [selectedEvidence, setSelectedEvidence] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchViolations = async () => {
    setLoading(true);

    try {
      const response = await axios.get(`${API_BASE}/violations`, {
        params: {
          date: date || undefined,
          type: type || undefined,
          plate: plate || undefined,
        },
      });

      setViolations(response.data || []);
      setPage(1);
    } catch {
      addToast?.({
        type: "danger",
        title: "Could not load violations",
        message: "Check if FastAPI backend is running.",
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchViolations();
  }, []);

  const filteredViolations = useMemo(() => violations, [violations]);

  const totalPages = Math.max(1, Math.ceil(filteredViolations.length / 10));

  const paginatedRows = filteredViolations.slice((page - 1) * 10, page * 10);

  const openEvidence = (record) => {
    const paths = String(record.evidence_paths || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);

    setSelectedEvidence({
      caseId: record.id,
      paths,
    });
  };

  const downloadChallan = (caseId) => {
    window.open(`${API_BASE}/challan/${caseId}`, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-green-400/20 bg-gray-900/60 p-5 shadow-xl shadow-green-500/5">
        <div className="mb-5">
          <h1 className="text-2xl font-black text-white">Violations Log</h1>
          <p className="text-sm text-gray-500">
            Search, filter, inspect evidence, and download challan PDFs.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
          <input
            type="date"
            value={date}
            onChange={(event) => setDate(event.target.value)}
            className="rounded-lg border border-gray-800 bg-gray-950 px-3 py-2 text-sm text-white outline-none ring-green-400/30 focus:ring-2"
          />

          <select
            value={type}
            onChange={(event) => setType(event.target.value)}
            className="rounded-lg border border-gray-800 bg-gray-950 px-3 py-2 text-sm text-white outline-none ring-green-400/30 focus:ring-2"
          >
            <option value="">All Types</option>
            <option value="seatbelt">Seatbelt</option>
            <option value="phone">Phone</option>
            <option value="speed">Speed</option>
            <option value="helmet">Helmet</option>
            <option value="wrong_way">Wrong Way</option>
            <option value="drowsiness">Drowsiness</option>
          </select>

          <input
            value={plate}
            onChange={(event) => setPlate(event.target.value.toUpperCase())}
            placeholder="Search plate..."
            className="rounded-lg border border-gray-800 bg-gray-950 px-3 py-2 text-sm uppercase text-white outline-none ring-green-400/30 placeholder:text-gray-600 focus:ring-2 md:col-span-2"
          />

          <button
            onClick={fetchViolations}
            className="rounded-lg bg-green-400 px-4 py-2 text-sm font-black uppercase tracking-wider text-gray-950 transition hover:bg-green-300"
          >
            Apply Filters
          </button>
        </div>
      </section>

      <section className="overflow-hidden rounded-2xl border border-gray-800 bg-gray-900/60 shadow-2xl shadow-black/20">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1050px] text-left text-sm">
            <thead className="border-b border-gray-800 bg-gray-950 text-xs uppercase tracking-wider text-gray-400">
              <tr>
                <th className="px-4 py-4">Case ID</th>
                <th className="px-4 py-4">Plate</th>
                <th className="px-4 py-4">Type</th>
                <th className="px-4 py-4">Time</th>
                <th className="px-4 py-4">Location</th>
                <th className="px-4 py-4">Fine</th>
                <th className="px-4 py-4">Status</th>
                <th className="px-4 py-4">Actions</th>
              </tr>
            </thead>

            <tbody className="divide-y divide-gray-800">
              {loading ? (
                <tr>
                  <td colSpan="8" className="px-4 py-10 text-center text-gray-500">
                    Loading violation records...
                  </td>
                </tr>
              ) : paginatedRows.length === 0 ? (
                <tr>
                  <td colSpan="8" className="px-4 py-10 text-center text-gray-500">
                    No violations found.
                  </td>
                </tr>
              ) : (
                paginatedRows.map((record) => (
                  <tr key={record.id} className="bg-gray-900/30 hover:bg-green-400/5">
                    <td className="max-w-[180px] truncate px-4 py-4 font-mono text-xs text-green-400">
                      {record.id}
                    </td>
                    <td className="px-4 py-4 font-black text-white">{record.plate}</td>
                    <td className="px-4 py-4 uppercase text-red-400">
                      {record.violation_type}
                    </td>
                    <td className="px-4 py-4 text-gray-300">{record.timestamp}</td>
                    <td className="px-4 py-4 text-gray-400">{record.location}</td>
                    <td className="px-4 py-4 font-bold text-red-400">
                      ₹{record.fine_amount}
                    </td>
                    <td className="px-4 py-4">
                      <span
                        className={`rounded-full border px-3 py-1 text-xs font-bold uppercase ${
                          statusStyles[record.status] ||
                          "border-gray-700 bg-gray-800 text-gray-300"
                        }`}
                      >
                        {record.status}
                      </span>
                    </td>
                    <td className="px-4 py-4">
                      <div className="flex gap-2">
                        <button
                          onClick={() => openEvidence(record)}
                          className="rounded-lg border border-green-400/30 px-3 py-2 text-xs font-bold text-green-400 transition hover:bg-green-400/10"
                        >
                          View Evidence
                        </button>

                        <button
                          onClick={() => downloadChallan(record.id)}
                          className="rounded-lg border border-red-500/30 px-3 py-2 text-xs font-bold text-red-400 transition hover:bg-red-500/10"
                        >
                          Download Challan
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="flex items-center justify-between border-t border-gray-800 bg-gray-950 px-4 py-4">
          <p className="text-sm text-gray-500">
            Page {page} of {totalPages} • {filteredViolations.length} records
          </p>

          <div className="flex gap-2">
            <button
              disabled={page === 1}
              onClick={() => setPage((prev) => Math.max(1, prev - 1))}
              className="rounded-lg border border-gray-700 px-3 py-2 text-sm text-gray-300 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Previous
            </button>

            <button
              disabled={page === totalPages}
              onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
              className="rounded-lg border border-gray-700 px-3 py-2 text-sm text-gray-300 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      </section>

      {selectedEvidence && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur">
          <div className="max-h-[90vh] w-full max-w-5xl overflow-y-auto rounded-2xl border border-green-400/20 bg-gray-950 p-5 shadow-2xl shadow-green-500/10">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h2 className="text-xl font-black text-white">Evidence Frames</h2>
                <p className="font-mono text-xs text-green-400">
                  Case ID: {selectedEvidence.caseId}
                </p>
              </div>

              <button
                onClick={() => setSelectedEvidence(null)}
                className="rounded-lg bg-red-500 px-4 py-2 text-sm font-bold text-white"
              >
                Close
              </button>
            </div>

            {selectedEvidence.paths.length === 0 ? (
              <div className="rounded-xl border border-gray-800 bg-gray-900 p-10 text-center text-gray-500">
                No evidence path stored for this record.
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                {selectedEvidence.paths.map((path, index) => (
                  <div
                    key={`${path}-${index}`}
                    className="overflow-hidden rounded-xl border border-gray-800 bg-gray-900"
                  >
                    <img
                      src={resolveEvidenceUrl(path)}
                      alt={`Evidence frame ${index + 1}`}
                      className="h-56 w-full object-cover"
                      onError={(event) => {
                        event.currentTarget.style.display = "none";
                      }}
                    />
                    <div className="border-t border-gray-800 p-3">
                      <p className="text-sm font-bold text-white">
                        Frame {index + 1}
                      </p>
                      <p className="break-all font-mono text-xs text-gray-500">
                        {path}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}