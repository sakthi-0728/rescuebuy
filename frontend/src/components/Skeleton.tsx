export function Skeleton({ height = 16, width = "100%" }: { height?: number; width?: string }) {
  return <div className="skeleton" style={{ height, width }} aria-hidden="true" />;
}

export function SkeletonPanel({ lines = 3, label = "Loading" }: { lines?: number; label?: string }) {
  return (
    <section className="panel" aria-busy="true" aria-label={label}>
      <Skeleton height={20} width="35%" />
      <div className="skeleton-stack">
        {Array.from({ length: lines }, (_, i) => (
          <Skeleton key={i} height={14} width={i === lines - 1 ? "60%" : "100%"} />
        ))}
      </div>
    </section>
  );
}
