import { useEffect, useRef, useState, type FormEvent } from "react";
import { useClerk, useUser } from "@clerk/clerk-react";
import { useLocation } from "react-router-dom";
import { Check, LoaderCircle, MessageSquare, Send, X } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n/provider";

const copy = {
  zh: {
    title: "和我们聊聊",
    trigger: "反馈",
    subtitle: "使用建议、遇到的问题，或你希望增加的功能。",
    kind: "这次想聊什么",
    feedback: "产品反馈",
    upgrade: "申请升级",
    contact: "邮箱或其他联系方式",
    contactHint: "例如邮箱、微信号；仅用于回复这次反馈",
    message: "你的反馈",
    placeholder: "告诉我们发生了什么，或者你希望怎样改进…",
    upgradeHint: "我想了解更多 AI 额度和会员方案。",
    send: "提交反馈",
    sending: "正在提交…",
    received: "已收到，谢谢你",
    saved: "反馈已保存。我们会通过你留下的联系方式回复。",
    request: "申请已保存，后续由人工联系确认，不会自动扣款或开通。",
    close: "关闭反馈",
    again: "再写一条",
    error: "暂时提交失败，内容已保留，请重试。",
    limit: "提交较频繁，请一小时后再试。",
    login: "登录后申请升级",
    privacy: "请勿填写密码或付款信息。仅发送你在这里填写的内容，不会附带私人日记。",
    required: "请填写联系方式和至少 5 个字符的反馈。"
  },
  en: {
    title: "Talk to us",
    trigger: "Feedback",
    subtitle: "Share an idea, report a problem, or tell us what you need.",
    kind: "What is this about?",
    feedback: "Product feedback",
    upgrade: "Request an upgrade",
    contact: "Email or another contact",
    contactHint: "Only used to reply to this request",
    message: "Your message",
    placeholder: "What happened, or what could we improve?",
    upgradeHint: "I'd like to learn about more AI credits and membership options.",
    send: "Send feedback",
    sending: "Sending…",
    received: "Received. Thank you!",
    saved: "Your feedback has been saved. We will reply using the contact you provided.",
    request:
      "Your request is saved for manual follow-up. No payment or membership is activated automatically.",
    close: "Close feedback",
    again: "Write another",
    error: "Could not submit. Your message is preserved; please retry.",
    limit: "Too many submissions. Please try again in an hour.",
    login: "Sign in to request an upgrade",
    privacy:
      "Do not include passwords or payment details. Only this form is sent; your private journal is not attached.",
    required: "Enter a contact and a message of at least 5 characters."
  },
  ja: {
    title: "ご意見をお聞かせください",
    trigger: "フィードバック",
    subtitle: "ご提案、不具合、追加してほしい機能など。",
    kind: "お問い合わせの種類",
    feedback: "フィードバック",
    upgrade: "アップグレード申請",
    contact: "メールまたはその他の連絡先",
    contactHint: "このお問い合わせへの返信にのみ使用します",
    message: "内容",
    placeholder: "何が起きましたか？改善してほしいことを教えてください。",
    upgradeHint: "AI クレジットと会員プランについて教えてください。",
    send: "送信",
    sending: "送信中…",
    received: "受け付けました",
    saved: "内容を保存しました。ご記入の連絡先に返信いたします。",
    request: "申請を保存しました。確認後にご連絡します。自動課金や会員登録は行いません。",
    close: "閉じる",
    again: "もう一件書く",
    error: "送信できませんでした。内容は保持されています。再試行してください。",
    limit: "送信が多すぎます。1時間後にお試しください。",
    login: "ログインしてアップグレードを申請",
    privacy:
      "パスワードや支払情報を記入しないでください。このフォームのみ送信し、日記は添付しません。",
    required: "連絡先と5文字以上の内容を入力してください。"
  }
};

export function FeedbackWidget() {
  const { locale } = useI18n();
  const c = copy[locale];
  const { user, isSignedIn } = useUser();
  const { openSignIn } = useClerk();
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<"feedback" | "upgrade">("feedback");
  const [contact, setContact] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [receipt, setReceipt] = useState("");
  const request = useRef<{ key: string; id: string } | null>(null);
  useEffect(() => {
    const show = () => {
      setKind("upgrade");
      setReceipt("");
      setError("");
      setOpen(true);
    };
    window.addEventListener("sign-atlas-feedback", show);
    return () => window.removeEventListener("sign-atlas-feedback", show);
  }, []);
  useEffect(() => {
    setOpen(false);
    setMessage("");
    setReceipt("");
    setContact(user?.primaryEmailAddress?.emailAddress ?? "");
    request.current = null;
  }, [user?.id, user?.primaryEmailAddress?.emailAddress]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (contact.trim().length < 3 || message.trim().length < 5) {
      setError(c.required);
      return;
    }
    const key = JSON.stringify([user?.id, kind, contact.trim(), message.trim()]);
    if (request.current?.key !== key) request.current = { key, id: crypto.randomUUID() };
    setBusy(true);
    setError("");
    try {
      const result = await api.submitFeedback({
        request_id: request.current.id,
        kind,
        contact: contact.trim(),
        message: message.trim()
      });
      setReceipt(result.id);
      setMessage("");
      request.current = null;
    } catch (caught) {
      setError(caught instanceof ApiError && caught.status === 429 ? c.limit : c.error);
    } finally {
      setBusy(false);
    }
  }

  const field =
    "mt-2 w-full rounded-xl border border-white/20 bg-[#231c2c] px-3 py-3 text-base text-cream outline-none focus:border-gold focus:ring-2 focus:ring-gold/25 disabled:opacity-60";
  return (
    <div
      className={`fixed right-4 z-[70] sm:right-6 ${pathname.startsWith("/app") ? "bottom-[calc(5.5rem+env(safe-area-inset-bottom))] lg:bottom-5 lg:left-[268px] lg:right-auto" : "bottom-[calc(1.5rem+env(safe-area-inset-bottom))]"}`}
    >
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            aria-label={c.trigger}
            className="flex min-h-12 items-center gap-2 rounded-full border border-gold/45 bg-[#211a2a] px-4 text-sm font-medium text-gold-light shadow-lg outline-none transition-[background-color,transform] duration-150 hover:bg-[#30253b] focus-visible:ring-2 focus-visible:ring-gold active:scale-[0.97] motion-reduce:transition-none"
          >
            <MessageSquare size={19} />
            <span className="hidden sm:inline">{c.trigger}</span>
          </button>
        </PopoverTrigger>
        <PopoverContent
          side="top"
          align="end"
          collisionPadding={12}
          aria-labelledby="feedback-title"
          className="!z-[80] max-h-[min(75dvh,var(--radix-popover-content-available-height))] w-[min(380px,calc(100vw-24px))] overflow-y-auto rounded-2xl !bg-[#17121f] !p-5 text-cream shadow-[0_20px_70px_#0008]"
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            document.getElementById("feedback-message")?.focus({ preventScroll: true });
          }}
        >
          <div className="mb-2 flex items-center justify-between gap-4">
            <h2 id="feedback-title" className="text-lg font-medium">
              {c.title}
            </h2>
            <button
              type="button"
              aria-label={c.close}
              onClick={() => setOpen(false)}
              className="grid size-11 shrink-0 place-items-center rounded-lg text-cream/65 hover:bg-white/10 focus-visible:outline-gold"
            >
              <X size={18} />
            </button>
          </div>
          {receipt ? (
            <div role="status" className="py-5">
              <Check className="mb-4 text-gold" />
              <h3 className="text-lg">{c.received}</h3>
              <p className="mt-3 text-sm leading-7 text-cream/70">
                {kind === "upgrade" ? c.request : c.saved}
              </p>
              <p className="mt-3 font-mono text-xs text-cream/50">#{receipt.slice(0, 8)}</p>
              <button
                type="button"
                className="mt-6 min-h-11 text-sm text-gold underline"
                onClick={() => setReceipt("")}
              >
                {c.again}
              </button>
            </div>
          ) : (
            <form onSubmit={(event) => void submit(event)}>
              <p className="mb-4 text-sm leading-6 text-cream/65">{c.subtitle}</p>
              <label className="block text-sm" htmlFor="feedback-kind">
                {c.kind}
              </label>
              <select
                id="feedback-kind"
                value={kind}
                disabled={busy}
                onChange={(event) => setKind(event.target.value as "feedback" | "upgrade")}
                className={field}
              >
                <option value="feedback">{c.feedback}</option>
                <option value="upgrade">{c.upgrade}</option>
              </select>
              <label className="mt-4 block text-sm" htmlFor="feedback-contact">
                {c.contact}
              </label>
              <input
                id="feedback-contact"
                autoComplete="email"
                maxLength={320}
                required
                minLength={3}
                value={contact}
                onChange={(event) => setContact(event.target.value)}
                disabled={busy}
                aria-describedby="feedback-contact-hint"
                className={field}
              />
              <p id="feedback-contact-hint" className="mt-1.5 text-xs text-cream/55">
                {c.contactHint}
              </p>
              <label className="mt-4 block text-sm" htmlFor="feedback-message">
                {c.message}
              </label>
              <textarea
                id="feedback-message"
                rows={4}
                required
                minLength={5}
                maxLength={4000}
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                placeholder={kind === "upgrade" ? c.upgradeHint : c.placeholder}
                disabled={busy}
                className={`${field} resize-y`}
              />
              <p className="mt-2 text-xs leading-5 text-cream/55">{c.privacy}</p>
              {error && (
                <p role="alert" className="mt-3 text-sm text-red-300">
                  {error}
                </p>
              )}
              {kind === "upgrade" && !isSignedIn ? (
                <button
                  type="button"
                  onClick={() => void openSignIn()}
                  className="mt-4 min-h-11 w-full rounded-xl bg-gold px-4 py-3 font-medium text-night"
                >
                  {c.login}
                </button>
              ) : (
                <button
                  disabled={busy}
                  type="submit"
                  className="mt-4 flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-gold px-4 py-3 font-medium text-night hover:bg-gold-light disabled:opacity-60"
                >
                  {busy ? (
                    <LoaderCircle size={16} className="animate-spin motion-reduce:animate-none" />
                  ) : (
                    <Send size={16} />
                  )}{" "}
                  {busy ? c.sending : c.send}
                </button>
              )}
            </form>
          )}
        </PopoverContent>
      </Popover>
    </div>
  );
}
