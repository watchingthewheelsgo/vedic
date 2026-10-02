import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AdminMembership } from "../components/AdminMembership";
import { api } from "../api";
import type { FeedbackItem } from "../lib/feedback";

export function AdminFeedback() {
  const [memberId, setMemberId] = useState("");
  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const load = useCallback(async () => {
    setError("");
    try {
      setItems((await api.listFeedback()).items);
    } catch {
      setError("反馈加载失败，请重试。");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  return (
    <main className="mx-auto max-w-4xl px-5 py-10 text-cream">
      <Link to="/app/settings" className="text-sm text-gold">
        ← 返回个人空间
      </Link>
      <div className="my-7 flex items-center justify-between">
        <h1 className="text-3xl">反馈与升级申请</h1>
        <button className="min-h-11 text-gold" onClick={() => void load()}>
          刷新
        </button>
      </div>
      <p className="mb-6 text-sm text-cream/60">
        仅管理员可见，显示最近 100 条。处理升级前请核对账号；标记处理不会开通会员。
      </p>
      <AdminMembership selectedUserId={memberId} />
      {error && (
        <p role="alert" className="mb-5 text-red-300">
          {error}
        </p>
      )}
      {loading ? (
        <p role="status">加载中…</p>
      ) : !items.length ? (
        <p>暂无反馈。</p>
      ) : (
        <div className="space-y-4">
          {items.map((item) => (
            <article key={item.id} className="rounded-2xl border border-white/15 bg-[#17121f] p-5">
              <div className="flex flex-wrap justify-between gap-3 text-sm">
                <span className="text-gold">
                  {item.kind === "upgrade" ? "升级申请" : "产品反馈"} ·{" "}
                  {item.status === "resolved" ? "已处理" : "待处理"}
                </span>
                <time className="text-cream/55">{new Date(item.createdAt).toLocaleString()}</time>
              </div>
              <p className="mt-4 whitespace-pre-wrap break-words text-sm leading-7">
                {item.message}
              </p>
              <p className="mt-4 break-all text-sm text-cream/75">联系方式：{item.contact}</p>
              <p className="mt-2 break-all text-xs text-cream/55">
                账号：{item.ownerUserId ?? "未登录访客"}
              </p>
              {item.ownerUserId && (
                <button
                  className="mt-3 mr-5 min-h-11 text-sm text-gold underline"
                  onClick={() => {
                    setMemberId(item.ownerUserId!);
                    document.getElementById("membership-admin")?.scrollIntoView({ block: "start" });
                  }}
                >
                  管理此用户会员
                </button>
              )}
              <button
                disabled={busy === item.id}
                className="mt-4 min-h-11 text-sm text-gold underline disabled:opacity-50"
                onClick={async () => {
                  setBusy(item.id);
                  try {
                    await api.resolveFeedback(
                      item.id,
                      item.status === "open" ? "resolved" : "open"
                    );
                    await load();
                  } catch {
                    setError("更新失败，请重试。");
                  } finally {
                    setBusy("");
                  }
                }}
              >
                {busy === item.id ? "保存中…" : item.status === "open" ? "标记已处理" : "重新打开"}
              </button>
            </article>
          ))}
        </div>
      )}
    </main>
  );
}
