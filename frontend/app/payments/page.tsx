"use client";

import React, { useState } from "react";

const API_BASE =
  (typeof window !== "undefined"
    ? (window as any).ENV?.NEXT_PUBLIC_API_URL
    : process.env.NEXT_PUBLIC_API_URL) || ""; // Backend API URL

export default function PaymentsPage() {
  const [priceId, setPriceId] = useState<string>("");
  const [quantity, setQuantity] = useState<number>(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startPayment = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : null;
      const resp = await fetch(`${API_BASE}/api/payments/link`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        credentials: "include",
        body: JSON.stringify({ price_id: priceId || undefined, quantity }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ error: resp.statusText }));
        throw new Error(err.error?.message || JSON.stringify(err));
      }
      const data = await resp.json();
      if (data?.url) {
        window.location.href = data.url;
      } else {
        throw new Error("No payment link returned");
      }
    } catch (e: any) {
      setError(e?.message || "Failed to start payment");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-xl mx-auto py-12 px-4">
      <h1 className="text-2xl font-semibold mb-4">Payments</h1>
      <p className="text-sm text-gray-600 mb-6">
        Select a plan and proceed to Stripe for checkout. Credits will be awarded after payment completion.
      </p>

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">Stripe Price ID</label>
          <input
            className="w-full border rounded px-3 py-2"
            placeholder="Leave blank to use default PRICE_ID_STARTER"
            value={priceId}
            onChange={(e) => setPriceId(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Quantity</label>
          <input
            type="number"
            min={1}
            className="w-32 border rounded px-3 py-2"
            value={quantity}
            onChange={(e) => setQuantity(parseInt(e.target.value || "1", 10))}
          />
        </div>
        {error && <div className="text-sm text-red-600">{error}</div>}
        <button
          className="bg-black text-white rounded px-4 py-2 disabled:opacity-60"
          disabled={loading}
          onClick={startPayment}
        >
          {loading ? "Redirecting..." : "Checkout with Stripe"}
        </button>
      </div>
    </div>
  );
}
