export function LoginFormSkeleton() {
  return (
    <form aria-describedby="implementation-status" className="space-y-6">
      <div>
        <label className="block text-sm font-medium" htmlFor="email">
          校园邮箱
        </label>
        <input
          autoComplete="email"
          className="mt-2 min-h-11 w-full border border-[var(--color-border-strong)] bg-[var(--color-surface)] px-3 text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]"
          id="email"
          inputMode="email"
          name="email"
          placeholder="name@hkust-gz.edu.cn"
          type="email"
        />
        <p className="mt-2 text-xs text-[var(--color-text-muted)]">
          仅接受 @hkust-gz.edu.cn 邮箱
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium" htmlFor="password">
          密码
        </label>
        <input
          autoComplete="current-password"
          className="mt-2 min-h-11 w-full border border-[var(--color-border-strong)] bg-[var(--color-surface)] px-3 text-[var(--color-text-primary)]"
          id="password"
          name="password"
          type="password"
        />
      </div>

      <button
        className="min-h-11 w-full cursor-not-allowed bg-[var(--color-accent)] px-5 font-medium text-white opacity-55"
        disabled
        type="button"
      >
        登录服务尚未接入
      </button>

      <p
        className="border-l-2 border-[var(--color-warning)] bg-[var(--color-surface)] px-4 py-3 text-sm text-[var(--color-text-secondary)]"
        id="implementation-status"
        role="status"
      >
        当前已完成工程与视觉骨架。注册、邮箱验证和登录将在认证阶段接入，页面不会伪造成功状态。
      </p>
    </form>
  );
}
