export function openUpgradeRequest() {
  window.dispatchEvent(new CustomEvent("sign-atlas-feedback", { detail: "upgrade" }));
}

export type FeedbackItem = {
  id: string;
  kind: "feedback" | "upgrade";
  contact: string;
  message: string;
  ownerUserId: string | null;
  status: "open" | "resolved";
  createdAt: string;
};

export function openFeedback() {
  window.dispatchEvent(new CustomEvent("sign-atlas-feedback", { detail: { kind: "feedback" } }));
}
