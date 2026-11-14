"use client";

import * as React from "react";
import { AlertCircle, ArrowRight, CircleSlash, RotateCcw } from "lucide-react";
import { NumberRoll } from "./number-roll";
import { TextMorph } from "./text-morph";

/* ─────────────────────────────────────────────────────────
 * TASK PROGRESS: work that takes minutes, not seconds
 *
 *   running    phases fill left to right; the current one sweeps
 *              and its label shimmers; timer and stats roll; Cancel
 *   done       the last bar fills, a check draws itself beside the
 *              title, the timer reads "Hoàn tất 12s"; Cancel grows
 *              into the open action
 *   error      the failed phase and its label turn red, the reason
 *              opens in below; the button becomes Retry
 *   cancelled  stopped by the user; the button folds away
 *
 * Title, stats, timer and the one button share the first row; the
 * phase labels already say where it is, so there is no status line. For deep
 * research, long builds and batch jobs. Tell people they can
 * leave; the card is what they come back to.
 * ───────────────────────────────────────────────────────── */

export type TaskProgressStatus = "running" | "done" | "error" | "cancelled";

export interface TaskStat {
  label: string;
  /** Numbers roll when they change. */
  value: React.ReactNode;
}

export interface TaskProgressProps extends Omit<React.HTMLAttributes<HTMLDivElement>, "title"> {
  title: string;
  status: TaskProgressStatus;
  /** The stages, e.g. ["Searching", "Reading", "Writing"]. */
  phases: string[];
  /** Index of the current phase. */
  phase: number;
  /** Start time (ms); shows a live timer. */
  startedAt?: number;
  /** Total time (ms), if you know it once finished. */
  duration?: number;
  stats?: TaskStat[];
  /** A line under the progress, e.g. "You can close this tab. We'll keep going." */
  message?: string;
  onCancel?: () => void;
  onOpen?: () => void;
  openLabel?: string;
  errorText?: string;
  onRetry?: () => void;
}

const MORPH = "cubic-bezier(0.16,1,0.3,1)";
const FOCUS = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40";
// A light that sweeps across the label. A mask, not a text clip, so it reaches letters that are mid-morph.
const SHEEN =
  "text-foreground [mask-image:linear-gradient(90deg,rgb(0_0_0/0.45)_35%,#000_50%,rgb(0_0_0/0.45)_65%)] [mask-size:200%_100%] animate-[ui-sheen_1.4s_linear_infinite] motion-reduce:animate-none motion-reduce:[mask-image:none] motion-reduce:text-foreground/70";
const TWO_DIGITS = { minimumIntegerDigits: 2 };

const reducedQuery = "(prefers-reduced-motion: reduce)";
const subscribeReduced = (onChange: () => void) => {
  const query = window.matchMedia(reducedQuery);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
};
const useReducedMotion = () =>
  React.useSyncExternalStore(subscribeReduced, () => window.matchMedia(reducedQuery).matches, () => false);

/** Icons trade places through a blur: the old one shrinks away as the new one grows in. */
const swap = (on: boolean, reduced: boolean): React.CSSProperties => ({
  opacity: on ? 1 : 0,
  transform: on ? "none" : "scale(0.6)",
  filter: on ? "none" : "blur(3px)",
  transition: reduced ? "none" : `opacity 260ms ${MORPH}, transform 380ms ${MORPH}, filter 260ms ${MORPH}`,
});

function formatTime(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

/** A piece of a line that opens out of nothing and folds back into it. */
function Reveal({ show, reduced, className = "", children }: { show: boolean; reduced: boolean; className?: string; children: React.ReactNode }) {
  return (
    <span
      aria-hidden={!show || undefined}
      className={`grid ${className}`}
      style={{
        gridTemplateColumns: show ? "1fr" : "0fr",
        opacity: show ? 1 : 0,
        filter: show ? "none" : "blur(3px)",
        transition: reduced ? "none" : `grid-template-columns 460ms ${MORPH}, opacity ${show ? "320ms" : "160ms"} ${MORPH}, filter 320ms ${MORPH}`,
      }}
    >
      <span className="min-w-0 whitespace-nowrap [clip-path:inset(-4px_-2px)]">{children}</span>
    </span>
  );
}

/** A block that opens to its height and folds back to nothing. */
function Fold({ show, reduced, children }: { show: boolean; reduced: boolean; children: React.ReactNode }) {
  return (
    <div
      aria-hidden={!show || undefined}
      className="grid"
      style={{
        gridTemplateRows: show ? "1fr" : "0fr",
        opacity: show ? 1 : 0,
        transition: reduced ? "none" : `grid-template-rows 460ms ${MORPH}, opacity ${show ? "320ms" : "160ms"} ${MORPH}`,
      }}
    >
      <div className="min-h-0 overflow-hidden">{children}</div>
    </div>
  );
}

/** Seconds that roll up as they pass; minutes slide open at the first minute. */
function Elapsed({ ms, reduced }: { ms: number; reduced: boolean }) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  return (
    <span className="inline-flex items-baseline">
      <Reveal show={minutes > 0} reduced={reduced}>
        <NumberRoll value={minutes} suffix="m" duration={500} />
        &nbsp;
      </Reveal>
      <NumberRoll value={minutes ? total % 60 : total} format={minutes ? TWO_DIGITS : undefined} suffix="s" direction="up" duration={500} />
    </span>
  );
}

function DrawnCheck({ drawn, reduced }: { drawn: boolean; reduced: boolean }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" className="size-3.5">
      <path
        d="M3.5 8.5 6.5 11.5 12.5 4.5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        pathLength={1}
        strokeDasharray={1}
        style={{ strokeDashoffset: drawn ? 0 : 1, transition: drawn && !reduced ? `stroke-dashoffset 420ms ${MORPH} 200ms` : "none" }}
      />
    </svg>
  );
}

export function TaskProgress({
  title,
  status,
  phases,
  phase,
  startedAt,
  duration,
  stats,
  message,
  onCancel,
  onOpen,
  openLabel = "Xem kết quả",
  errorText,
  onRetry,
  className = "",
  ...props
}: TaskProgressProps) {
  const reduced = useReducedMotion();
  const running = status === "running";
  const [now, setNow] = React.useState(startedAt ?? 0);
  const [endedAt, setEndedAt] = React.useState<number | undefined>(undefined);
  const cardRef = React.useRef<HTMLDivElement>(null);
  const actionRef = React.useRef<HTMLButtonElement>(null);

  const [seenStartedAt, setSeenStartedAt] = React.useState(startedAt);
  if (startedAt !== seenStartedAt) {
    setSeenStartedAt(startedAt);
    setNow(startedAt ?? 0);
  }

  if (running && endedAt !== undefined) setEndedAt(undefined);

  React.useEffect(() => {
    if (!running) {
      if (endedAt !== undefined) return;
      const frame = requestAnimationFrame(() => setEndedAt(Date.now()));
      return () => cancelAnimationFrame(frame);
    }
    if (startedAt === undefined) return;
    const initial = window.setTimeout(() => setNow(Date.now()), 0);
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [running, startedAt, endedAt]);

  const elapsed = duration ?? (startedAt === undefined ? undefined : (running ? now : (endedAt ?? now)) - startedAt);
  const current = Math.min(Math.max(phase, 0), phases.length - 1);

  // The one button: Cancel while it runs, Retry after a failure, the result once done.
  const action =
    running && onCancel
      ? { kind: "cancel", label: "Hủy", run: onCancel }
      : status === "error" && onRetry
        ? { kind: "retry", label: "Thử lại", run: onRetry }
        : status === "done" && onOpen
          ? { kind: "open", label: openLabel, run: onOpen }
          : null;
  const [lastAction, setLastAction] = React.useState(action);
  if (action && (action.kind !== lastAction?.kind || action.label !== lastAction.label)) setLastAction(action);
  const shown = action ?? lastAction;
  const primary = action?.kind === "open";
  const hasAction = Boolean(action);

  // If the button folds away while focused (Cancel pressed), keep focus on the card instead of the page.
  React.useLayoutEffect(() => {
    if (!hasAction && document.activeElement === actionRef.current) cardRef.current?.focus({ preventScroll: true });
  }, [hasAction]);

  const outcome = status === "done" ? "Hoàn tất" : status === "cancelled" ? "Đã hủy" : null;
  const iconKey = status === "running" ? null : status;

  return (
    <div ref={cardRef} tabIndex={-1} className={`w-full rounded-xl border border-border bg-background px-4 py-3 outline-none ${className}`} {...props}>
      <div className="flex min-h-8 items-center justify-between gap-4">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
          <span className="flex min-w-0 items-center">
            <span
              aria-hidden="true"
              className="relative flex h-3.5 shrink-0 items-center justify-center"
              style={{ width: iconKey ? 14 : 0, marginRight: iconKey ? 6 : 0, transition: reduced ? "none" : `width 380ms ${MORPH}, margin 380ms ${MORPH}` }}
            >
              <span className="absolute inset-0 flex items-center justify-center text-emerald-600 dark:text-emerald-400" style={swap(iconKey === "done", reduced)}>
                <DrawnCheck drawn={iconKey === "done"} reduced={reduced} />
              </span>
              <span className="absolute inset-0 flex items-center justify-center text-red-500" style={swap(iconKey === "error", reduced)}>
                <AlertCircle className="size-3.5" />
              </span>
              <span className="absolute inset-0 flex items-center justify-center text-muted-foreground" style={swap(iconKey === "cancelled", reduced)}>
                <CircleSlash className="size-3.5" />
              </span>
            </span>
            <p className="truncate text-[13.5px] font-medium text-foreground">{title}</p>
          </span>
          {stats && stats.length > 0 && (
            <p className="flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-muted-foreground">
              {stats.map((s) => (
                <span key={s.label} className="inline-flex items-baseline gap-[0.3em]">
                  <span className="font-mono tabular-nums text-foreground">{typeof s.value === "number" ? <NumberRoll value={s.value} duration={700} /> : s.value}</span>
                  {s.label}
                </span>
              ))}
            </p>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-3">
          {elapsed !== undefined && (
            <span aria-hidden="true" className="inline-flex items-baseline gap-[0.3em] font-mono text-[11.5px] tabular-nums text-muted-foreground">
              {outcome && <span className="font-sans">{outcome}</span>}
              <Elapsed ms={elapsed} reduced={reduced} />
            </span>
          )}
          {shown && (
            <Reveal show={Boolean(action)} reduced={reduced} className="shrink-0">
              <span className="block p-0.5">
                <button
                  ref={actionRef}
                  type="button"
                  inert={!action}
                  onClick={() => action?.run()}
                  className={`cursor-pointer inline-flex h-7 items-center rounded-lg px-2.5 text-[12.5px] font-medium transition-[background-color,color,box-shadow,transform] duration-300 active:scale-[0.97] ${FOCUS} ${
                    primary ? "bg-primary text-primary-foreground hover:bg-primary/90" : "text-foreground shadow-[inset_0_0_0_1px_var(--border)] hover:bg-accent"
                  }`}
                >
                  <span
                    aria-hidden="true"
                    className="relative flex h-3 shrink-0 items-center justify-center overflow-hidden"
                    style={{ width: shown.kind === "retry" ? 12 : 0, marginRight: shown.kind === "retry" ? 6 : 0, transition: reduced ? "none" : `width 380ms ${MORPH}, margin 380ms ${MORPH}` }}
                  >
                    <RotateCcw className="size-3 shrink-0" style={swap(shown.kind === "retry", reduced)} />
                  </span>
                  <TextMorph>{shown.label}</TextMorph>
                  <span
                    aria-hidden="true"
                    className="relative flex h-3.5 shrink-0 items-center justify-center overflow-hidden"
                    style={{ width: shown.kind === "open" ? 14 : 0, marginLeft: shown.kind === "open" ? 6 : 0, transition: reduced ? "none" : `width 380ms ${MORPH}, margin 380ms ${MORPH}` }}
                  >
                    <ArrowRight className="size-3.5 shrink-0" style={swap(shown.kind === "open", reduced)} />
                  </span>
                </button>
              </span>
            </Reveal>
          )}
        </div>
      </div>

      {/* Each phase fills from the left when it's finished; the live one sweeps. */}
      <div className="mt-2 flex gap-1" aria-hidden="true">
        {phases.map((p, i) => {
          const complete = status === "done" || i < current;
          const failed = status === "error" && i === current;
          const live = running && i === current;
          return (
            <span key={p} className="relative h-1 flex-1 overflow-hidden rounded-full bg-border">
              <span
                className={`absolute inset-0 origin-left rounded-full transition-colors duration-300 ${failed ? "bg-red-500" : "bg-foreground"}`}
                style={{ transform: complete || failed ? "none" : "scaleX(0)", transition: reduced ? "none" : `transform 620ms ${MORPH}, background-color 300ms` }}
              />
              <span
                className={`absolute inset-y-0 left-0 w-2/5 rounded-full bg-foreground/60 motion-reduce:hidden ${live ? "animate-[ui-scan_1.6s_cubic-bezier(0.45,0,0.55,1)_infinite]" : ""}`}
                style={{ opacity: live ? 1 : 0, transition: reduced ? "none" : "opacity 300ms" }}
              />
            </span>
          );
        })}
      </div>

      <div aria-hidden="true" className="mt-1.5 flex gap-1 text-[11.5px]">
        {phases.map((p, i) => (
          <span
            key={p}
            className={`flex-1 truncate transition-colors duration-300 ${status === "error" && i === current ? "text-red-500" : running && i === current ? `font-medium ${SHEEN}` : "text-muted-foreground"}`}
          >
            {p}
          </span>
        ))}
      </div>

      <p role="status" aria-live="polite" className="sr-only">
        {status === "done"
          ? `${title} hoàn tất${elapsed !== undefined ? ` trong ${formatTime(elapsed)}` : ""}`
          : status === "error"
            ? `${title} thất bại. ${errorText ?? ""}`
            : status === "cancelled"
              ? `${title} đã hủy`
              : `${phases[current]}`}
      </p>

      {message && (
        <Fold show={running} reduced={reduced}>
          <p className="pt-1.5 text-[12px] text-muted-foreground">{message}</p>
        </Fold>
      )}
      <Fold show={status === "error"} reduced={reduced}>
        <p className="pt-1.5 text-[12.5px] text-red-500">{errorText ?? "Đã xảy ra lỗi giữa chừng."}</p>
      </Fold>
    </div>
  );
}
