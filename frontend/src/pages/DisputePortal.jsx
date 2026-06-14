import React, { useState } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export default function DisputePortal({ addToast }) {
  const [caseId, setCaseId] = useState("");
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [confirmation, setConfirmation] = useState(null);

  const submitDispute = async (event) => {
    event.preventDefault();

    if (!caseId.trim() || !reason.trim()) {
      addToast?.({
        type: "danger",
        title: "Missing details",
        message: "Enter both Case ID and dispute reason.",
      });
      return;
    }

    setLoading(true);
    setConfirmation(null);

    try {
      const response = await axios.post(`${API_BASE}/dispute/${caseId.trim()}`, {
        reason: reason.trim(),
      });

      setConfirmation(response.data);

      addToast?.({
        type: "success",
        title: "Dispute submitted",
        message: `Dispute ID: ${response.data.dispute_id}`,
      });

      setReason("");
    } catch {
      addToast?.({
        type: "danger",
        title: "Dispute failed",
        message: "Case ID not found or backend unavailable.",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_0.85fr]">
      <section className="rounded-2xl border border-green-400/20 bg-gray-900/60 p-6 shadow-xl shadow-green-500/5">
        <div className="mb-6">
          <h1 className="text-2xl font-black text-white">Dispute Portal</h1>
          <p className="text-sm text-gray-500">
            Submit a challan dispute for manual review.
          </p>
        </div>

        <form onSubmit={submitDispute} className="space-y-5">
          <div>
            <label className="mb-2 block text-sm font-bold text-gray-300">
              Case ID
            </label>
            <input
              value={caseId}
              onChange={(event) => setCaseId(event.target.value)}
              placeholder="Enter challan case ID"
              className="w-full rounded-xl border border-gray-800 bg-gray-950 px-4 py-3 font-mono text-sm text-green-400 outline-none ring-green-400/30 placeholder:text-gray-600 focus:ring-2"
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-bold text-gray-300">
              Reason for Dispute
            </label>
            <textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              rows="8"
              placeholder="Explain why this violation should be reviewed..."
              className="w-full resize-none rounded-xl border border-gray-800 bg-gray-950 px-4 py-3 text-sm text-white outline-none ring-green-400/30 placeholder:text-gray-600 focus:ring-2"
            />
          </div>

          <button
            disabled={loading}
            className="w-full rounded-xl bg-green-400 px-5 py-3 text-sm font-black uppercase tracking-wider text-gray-950 shadow-lg shadow-green-400/10 transition hover:bg-green-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Submitting..." : "Submit Dispute"}
          </button>
        </form>

        {confirmation && (
          <div className="mt-6 rounded-xl border border-green-400/30 bg-green-400/10 p-4">
            <h3 className="font-black text-green-400">Dispute Submitted Successfully</h3>
            <p className="mt-2 text-sm text-gray-300">
              Your dispute has been registered.
            </p>
            <p className="mt-2 font-mono text-sm text-green-400">
              Dispute ID: {confirmation.dispute_id}
            </p>
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-gray-800 bg-gray-900/60 p-6 shadow-2xl shadow-black/20">
        <h2 className="text-xl font-black text-white">Dispute FAQ</h2>

        <div className="mt-5 space-y-4">
          <div className="rounded-xl border border-gray-800 bg-gray-950/70 p-4">
            <h3 className="font-bold text-green-400">How long does review take?</h3>
            <p className="mt-2 text-sm leading-6 text-gray-400">
              Demo disputes are stored instantly as pending. In a real deployment,
              a traffic officer would review evidence, challan details, and your
              submitted reason.
            </p>
          </div>

          <div className="rounded-xl border border-gray-800 bg-gray-950/70 p-4">
            <h3 className="font-bold text-green-400">What should I include?</h3>
            <p className="mt-2 text-sm leading-6 text-gray-400">
              Mention why the violation is incorrect, include context like wrong
              vehicle detection, emergency situation, duplicate challan, or unclear
              evidence.
            </p>
          </div>

          <div className="rounded-xl border border-gray-800 bg-gray-950/70 p-4">
            <h3 className="font-bold text-green-400">Will fine status change?</h3>
            <p className="mt-2 text-sm leading-6 text-gray-400">
              Yes. Once a dispute is submitted, the violation status changes to
              disputed in the database.
            </p>
          </div>

          <div className="rounded-xl border border-red-500/20 bg-red-950/20 p-4">
            <h3 className="font-bold text-red-400">Important</h3>
            <p className="mt-2 text-sm leading-6 text-gray-400">
              This project is a prototype. Real traffic challan systems require
              certified devices, official approvals, audit logs, and government
              integration.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}