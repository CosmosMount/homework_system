import type { UserDirectionDistribution as Distribution } from "@/lib/api/types";

function percentage(count: number, total: number): number {
  if (total === 0) return 0;
  return Math.round((count / total) * 1000) / 10;
}

export function UserDirectionDistribution({
  distribution,
}: Readonly<{ distribution: Distribution }>) {
  const summary = [
    { label: "正常学生", value: distribution.total_active_students },
    { label: "已分组", value: distribution.assigned_active_students },
    { label: "未设置技术组", value: distribution.unassigned_active_students },
  ];
  const groups = [
    ...distribution.directions.map((direction) => ({
      id: direction.id,
      label: direction.name,
      count: direction.active_student_count,
      inactive: !direction.is_active,
    })),
    {
      id: "unassigned",
      label: "未设置技术组",
      count: distribution.unassigned_active_students,
      inactive: false,
    },
  ];

  return (
    <section
      aria-labelledby="user-direction-distribution-title"
      className="mt-8 border border-[var(--color-border)] bg-[var(--color-surface)] p-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-[var(--color-text-muted)]">
            PEOPLE / DIRECTIONS
          </p>
          <h2
            className="mt-2 text-xl font-medium"
            id="user-direction-distribution-title"
          >
            人员技术组分布
          </h2>
        </div>
        <p className="max-w-xl text-sm text-[var(--color-text-secondary)]">
          统计全部正常学生，不受下方搜索、活跃度、技术组筛选或分页影响。
        </p>
      </div>

      <dl className="mt-5 grid gap-3 sm:grid-cols-3">
        {summary.map((item) => (
          <div
            className="border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-4 py-3"
            key={item.label}
          >
            <dt className="text-sm text-[var(--color-text-muted)]">{item.label}</dt>
            <dd className="mt-1 text-2xl font-medium tabular-nums">{item.value}</dd>
          </div>
        ))}
      </dl>

      <ul className="mt-5 grid gap-3 lg:grid-cols-2">
        {groups.map((group) => {
          const share = percentage(group.count, distribution.total_active_students);
          return (
            <li className="border border-[var(--color-border)] p-4" key={group.id}>
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="font-medium">
                  {group.label}
                  {group.inactive ? (
                    <span className="ml-2 text-xs font-normal text-[var(--color-text-muted)]">
                      已停用
                    </span>
                  ) : null}
                </span>
                <span className="whitespace-nowrap tabular-nums">
                  {group.count} 人 · {share}%
                </span>
              </div>
              <div
                aria-hidden="true"
                className="mt-3 h-2 overflow-hidden bg-[var(--color-surface-raised)]"
              >
                <div
                  className="h-full bg-[var(--color-accent)]"
                  style={{ width: `${share}%` }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
