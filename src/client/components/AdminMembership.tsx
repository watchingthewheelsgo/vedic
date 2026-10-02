import { useEffect, useRef, useState } from "react";
import { api } from "../api";
export type Membership = {
  userId: string;
  email: string | null;
  role: string;
  active: boolean;
  expiresAt: string | null;
  monthlyLimit: number;
  history: { id: string; actor: string; action: string; note: string; createdAt: string }[];
};
const labels: Record<string, string> = { grant: "开通会员", renew: "续期", revoke: "关闭会员" };
export function AdminMembership({ selectedUserId }: { selectedUserId: string }) {
  const [query, setQuery] = useState("");
  const [member, setMember] = useState<Membership | null>(null);
  const [days, setDays] = useState(30);
  const [limit, setLimit] = useState(100);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [confirm, setConfirm] = useState(false);
  const sequence = useRef(0);
  const retry = useRef<{ key: string; id: string } | null>(null);
  async function load(id: string) {
    const seq = ++sequence.current;
    setBusy(true);
    setError("");
    setMessage("");
    setMember(null);
    setConfirm(false);
    try {
      const result = await api.getMembership(id);
      if (seq === sequence.current) {
        setMember(result);
        setLimit(result.active ? result.monthlyLimit : 100);
        setNote("");
      }
    } catch (e) {
      if (seq === sequence.current) setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      if (seq === sequence.current) setBusy(false);
    }
  }
  useEffect(() => {
    if (selectedUserId) {
      setQuery(selectedUserId);
      void load(selectedUserId);
    }
  }, [selectedUserId]);
  async function change(action: "grant" | "renew" | "revoke") {
    if (!member || busy) return;
    const id = member.userId;
    const seq = ++sequence.current;
    const data = { action, days, monthly_limit: limit, note: note.trim() };
    const key = JSON.stringify({ id, ...data });
    if (retry.current?.key !== key) retry.current = { key, id: crypto.randomUUID() };
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api.changeMembership(id, { ...data, request_id: retry.current.id });
      retry.current = null;
      if (seq !== sequence.current) return;
      setMessage(`${labels[action]}成功`);
      setMember(null);
      setConfirm(false);
      const result = await api.getMembership(id);
      if (seq === sequence.current) setMember(result);
    } catch (e) {
      if (seq === sequence.current) setError(e instanceof Error ? e.message : "操作失败，请重试");
    } finally {
      if (seq === sequence.current) setBusy(false);
    }
  }
  const valid =
    note.trim().length > 0 &&
    note.trim().length <= 500 &&
    Number.isInteger(days) &&
    days >= 1 &&
    days <= 366 &&
    Number.isInteger(limit) &&
    limit >= 10 &&
    limit <= 10000;
  const input =
    "mt-2 min-h-11 w-full rounded-lg border border-white/20 bg-[#17121f] px-3 text-cream";
  const button = "min-h-11 rounded-lg border border-gold/40 px-4 text-gold disabled:opacity-40";
  return (
    <section
      id="membership-admin"
      className="mb-8 scroll-mt-6 rounded-2xl border border-gold/25 bg-[#17121f] p-5"
    >
      <h2 className="text-xl">会员管理</h2>
      <p className="mt-2 text-sm text-cream/60">
        人工开通，不自动扣款。关闭会员保留记录和报告；开通、续期不会清零本月已用额度。
      </p>
      <form
        className="mt-4 flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          void load(query.trim());
        }}
      >
        <label className="min-w-0 flex-1 text-sm">
          Clerk 用户 ID
          <input
            className={input}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="user_…"
            required
            disabled={busy}
          />
        </label>
        <button className={button} disabled={busy || !query.trim()}>
          查询
        </button>
      </form>
      {busy && (
        <p className="mt-3 text-sm" role="status">
          处理中…
        </p>
      )}
      {error && (
        <p className="mt-3 text-red-300" role="alert">
          {error}
        </p>
      )}
      {message && (
        <p className="mt-3 text-gold" role="status">
          {message}
        </p>
      )}
      {member && (
        <div className="mt-5 space-y-4">
          <p className="break-all">
            {member.email ?? member.userId} · {member.active ? "会员" : "免费用户"}
          </p>
          <p className="break-all text-xs text-cream/60">账号：{member.userId}</p>
          <p className="text-sm text-cream/70">
            {member.expiresAt
              ? `到期时间：${new Date(member.expiresAt).toLocaleString()}`
              : "尚未开通过会员"}{" "}
            · {member.active ? member.monthlyLimit : 10} 点/月
          </p>
          {member.role === "admin" && (
            <p className="text-sm text-gold">此账号是管理员，AI 额度豁免，不受会员开关影响。</p>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-sm">
              {member.active ? "续期天数" : "有效天数"}
              <input
                type="number"
                min={1}
                max={366}
                className={input}
                value={days}
                disabled={busy}
                onChange={(e) => setDays(Number(e.target.value))}
              />
            </label>
            <label className="text-sm">
              每月 AI 额度
              <input
                type="number"
                min={10}
                max={10000}
                className={input}
                value={limit}
                disabled={busy}
                onChange={(e) => setLimit(Number(e.target.value))}
              />
            </label>
          </div>
          <label className="block text-sm">
            操作备注（必填）
            <input
              className={input}
              maxLength={500}
              value={note}
              disabled={busy}
              onChange={(e) => setNote(e.target.value)}
              placeholder="例如：已核实升级申请"
            />
          </label>
          <div className="flex flex-wrap gap-3">
            <button
              className={button}
              disabled={busy || !valid}
              onClick={() => void change(member.active ? "renew" : "grant")}
            >
              {member.active ? "续期会员" : "开通会员"}
            </button>
            {member.active && (
              <button className={button} disabled={busy || !valid} onClick={() => setConfirm(true)}>
                关闭会员
              </button>
            )}
          </div>
          {confirm && (
            <div className="rounded-lg border border-red-300/30 p-4">
              <p className="mb-3 text-sm">
                确认立即关闭 {member.email ?? member.userId} 的会员？将恢复免费额度，已有内容保留。
              </p>
              <button
                className={button}
                disabled={busy || !valid}
                onClick={() => void change("revoke")}
              >
                确认关闭
              </button>
              <button className="ml-4 min-h-11" disabled={busy} onClick={() => setConfirm(false)}>
                取消
              </button>
            </div>
          )}
          <details>
            <summary className="cursor-pointer py-2 text-sm text-gold">
              最近操作记录（{member.history.length}）
            </summary>
            <ul className="space-y-3">
              {member.history.map((h) => (
                <li
                  className="break-words border-t border-white/10 pt-3 text-xs leading-6 text-cream/65"
                  key={h.id}
                >
                  {labels[h.action]} · {new Date(h.createdAt).toLocaleString()}
                  <br />
                  操作人：{h.actor}
                  <br />
                  {h.note}
                </li>
              ))}
            </ul>
          </details>
        </div>
      )}
    </section>
  );
}
