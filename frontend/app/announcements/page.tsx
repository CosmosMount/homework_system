import Link from "next/link";
import { redirect } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { buttonClassName, inputClassName } from "@/components/ui/form-controls";
import { getAnnouncements, getDashboard, requireUser } from "@/lib/api/server";
import { formatDateTime } from "@/lib/format";

type AnnouncementListPageProps = Readonly<{
  searchParams: Promise<{
    q?: string;
    unread?: string;
    page?: string;
  }>;
}>;

function pageHref(page: number, query: string, unread: boolean): string {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (unread) params.set("unread", "true");
  if (page > 1) params.set("page", String(page));
  const suffix = params.toString();
  return suffix ? "/announcements?" + suffix : "/announcements";
}

export default async function AnnouncementsPage({
  searchParams,
}: AnnouncementListPageProps) {
  const [user, dashboard, filters] = await Promise.all([
    requireUser(),
    getDashboard(),
    searchParams,
  ]);
  if (user.role === "admin") {
    redirect("/admin/announcements");
  }

  const query = (filters.q ?? "").trim().slice(0, 200);
  const unread = filters.unread === "true";
  const requestedPage = Number(filters.page ?? "1");
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0
    ? requestedPage
    : 1;
  const apiParams = new URLSearchParams({
    page: String(page),
    page_size: "20",
  });
  if (query) apiParams.set("query", query);
  if (unread) apiParams.set("unread", "true");
  const announcements = await getAnnouncements(apiParams.toString());
  const hasNext = page * announcements.page_size < announcements.total;

  return (
    <AppShell unreadCount={dashboard.unread_count} user={user}>
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        STUDENT / ANNOUNCEMENTS
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">通知中心</h1>
      <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
        这里只显示已经发布且与你届次、方向匹配的通知；归档内容不会出现在默认列表中。
      </p>

      <form className="mt-8 grid gap-4 border border-[var(--color-border)] bg-[var(--color-surface)] p-5 md:grid-cols-[minmax(0,1fr)_auto_auto] md:items-end">
        <label className="text-sm font-medium" htmlFor="announcement-search">
          搜索标题或摘要
          <input
            className={inputClassName}
            defaultValue={query}
            id="announcement-search"
            maxLength={200}
            name="q"
            placeholder="输入关键词"
            type="search"
          />
        </label>
        <label className="flex min-h-11 items-center gap-2 border border-[var(--color-border-strong)] px-4 text-sm">
          <input defaultChecked={unread} name="unread" type="checkbox" value="true" />
          只看未读
        </label>
        <button
          className={buttonClassName}
          type="submit"
        >
          筛选
        </button>
      </form>

      <p className="mt-6 text-sm text-[var(--color-text-muted)]">
        共 {announcements.total} 条结果
      </p>
      {announcements.items.length ? (
        <div className="mt-4 space-y-3">
          {announcements.items.map((announcement) => (
            <article
              className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5 transition hover:border-[var(--color-border-strong)]"
              key={announcement.id}
            >
              <Link className="block" href={"/announcements/" + announcement.id}>
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex flex-wrap gap-2 font-mono text-xs">
                      {announcement.is_pinned ? (
                        <span className="bg-[var(--color-accent-fill)] px-2 py-0.5 text-white">
                          置顶
                        </span>
                      ) : null}
                      {announcement.is_unread ? (
                        <span className="border border-[var(--color-accent)] px-2 py-0.5 text-[var(--color-accent-hover)]">
                          未读
                        </span>
                      ) : null}
                      {announcement.has_attachments ? (
                        <span className="border border-[var(--color-border-strong)] px-2 py-0.5">
                          含附件
                        </span>
                      ) : null}
                    </div>
                    <h2 className="mt-3 text-xl font-medium">{announcement.title}</h2>
                    <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
                      {announcement.summary}
                    </p>
                  </div>
                  <time
                    className="font-mono text-xs text-[var(--color-text-muted)]"
                    dateTime={announcement.published_at}
                  >
                    {formatDateTime(announcement.published_at)}
                  </time>
                </div>
              </Link>
            </article>
          ))}
        </div>
      ) : (
        <p className="mt-4 border border-dashed border-[var(--color-border-strong)] p-8 text-center text-[var(--color-text-muted)]">
          没有符合当前筛选条件的通知。
        </p>
      )}

      <nav aria-label="通知分页" className="mt-8 flex items-center justify-between">
        {page > 1 ? (
          <Link
            className="min-h-11 border border-[var(--color-border-strong)] px-5 py-2"
            href={pageHref(page - 1, query, unread)}
          >
            ← 上一页
          </Link>
        ) : (
          <span />
        )}
        <span className="font-mono text-xs text-[var(--color-text-muted)]">
          第 {page} 页
        </span>
        {hasNext ? (
          <Link
            className="min-h-11 border border-[var(--color-border-strong)] px-5 py-2"
            href={pageHref(page + 1, query, unread)}
          >
            下一页 →
          </Link>
        ) : (
          <span />
        )}
      </nav>
    </AppShell>
  );
}
