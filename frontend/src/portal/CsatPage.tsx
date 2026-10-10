import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { Button, Card, ErrorMsg, inputCls } from "../ui";

const WORDS = ["Very unhappy", "Unhappy", "Okay", "Happy", "Very happy"];

/** Opened from the satisfaction email. The token and rating live in the URL fragment, which the
 *  browser never sends to a server; nothing is recorded until the person confirms here. */
function readLink() {
  const p = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const rating = Number(p.get("rating"));
  return { token: p.get("token") ?? "", rating: rating >= 1 && rating <= 5 ? rating : 0 };
}

export default function CsatPage() {
  const [{ token, rating: initial }] = useState(readLink);
  const [rating, setRating] = useState(initial);
  const [comment, setComment] = useState("");
  const send = useMutation({
    mutationFn: () => api<{ ticket_number: number }>("/csat/respond", { method: "POST", json: { token, rating, comment: comment || null } }),
    onSuccess: () => window.history.replaceState(null, "", "/csat"), // drop the used token from the address bar
  });
  return (
    <div className="mx-auto max-w-lg space-y-4 p-6">
      <h1 className="text-2xl font-bold tracking-tight">How did we do?</h1>
      {!token ? (
        <p className="text-sm text-red-700">This link is not complete. Please use the link from your email.</p>
      ) : send.isSuccess ? (
        <Card title="Thank you">
          <p className="text-sm">Your feedback on request #{send.data.ticket_number} has been recorded. You can close this page.</p>
        </Card>
      ) : (
        <Card title="Your rating">
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Rating">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                type="button"
                role="radio"
                aria-checked={rating === n}
                onClick={() => setRating(n)}
                className={`rounded-lg border px-3 py-2 text-sm ${rating === n ? "border-blue-600 bg-blue-600 text-white" : "border-slate-300 bg-surface"}`}
              >
                {n} · {WORDS[n - 1]}
              </button>
            ))}
          </div>
          <label className="mt-3 block text-sm font-medium text-slate-700">
            Anything you would like to add? (optional)
            <textarea className={`${inputCls} mt-1`} rows={4} maxLength={2000} value={comment} onChange={(e) => setComment(e.target.value)} />
          </label>
          <ErrorMsg error={send.error} />
          <div className="mt-3">
            <Button disabled={!rating || send.isPending} onClick={() => send.mutate()}>Send feedback</Button>
          </div>
        </Card>
      )}
    </div>
  );
}
