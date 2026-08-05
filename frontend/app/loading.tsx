export default function Loading() {
  return (
    <div className="flex min-h-[60dvh] items-center justify-center">
      <div className="flex items-center gap-3 text-muted">
        <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-brand-500" />
        <span className="text-sm">Loading…</span>
      </div>
    </div>
  );
}
