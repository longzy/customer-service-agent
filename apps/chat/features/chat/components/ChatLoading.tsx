export function ChatLoading() {
  return (
    <main className="grid min-h-dvh place-items-center bg-bg font-sans" aria-busy="true">
      <p className="m-0 flex items-center gap-2 text-sm text-text-3">
        <span
          aria-hidden="true"
          className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-border border-t-accent motion-reduce:animate-none"
        />
        加载中…
      </p>
    </main>
  );
}
