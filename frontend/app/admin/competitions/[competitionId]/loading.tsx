export default function AdminCompetitionLoading() {
  return (
    <main
      aria-busy="true"
      aria-label="正在加载赛事管理页"
      className="mx-auto w-full max-w-7xl px-5 py-12 sm:px-8"
    >
      <div className="h-4 w-52 animate-pulse bg-[var(--color-surface-hover)]" />
      <div className="mt-5 h-10 w-64 animate-pulse bg-[var(--color-surface-hover)]" />
      <div className="mt-8 grid gap-8 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="h-[34rem] animate-pulse border border-[var(--color-border)] bg-[var(--color-surface)]" />
        <div className="h-72 animate-pulse border border-[var(--color-border)] bg-[var(--color-surface)]" />
      </div>
    </main>
  );
}
