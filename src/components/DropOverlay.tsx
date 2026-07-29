export function DropOverlay({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <div className="drop-overlay" aria-live="polite">
      <span>松手喂给耄耋</span>
      <small>文件会进入系统回收站，可恢复</small>
    </div>
  );
}
