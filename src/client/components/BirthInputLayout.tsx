import type { ReactNode } from "react";
import { cn } from "../lib/cn";

type BirthInputStep = {
  label: string;
  index: number;
  active?: boolean;
};

export function BirthInputLayout({
  navControls,
  backLabel,
  title,
  subtitle,
  icon,
  badge,
  steps,
  maxWidthClass = "max-w-[560px]",
  children,
  onBack
}: {
  navControls: ReactNode;
  backLabel: string;
  title: string;
  subtitle: string;
  icon: ReactNode;
  badge?: ReactNode;
  steps?: BirthInputStep[];
  maxWidthClass?: string;
  children: ReactNode;
  onBack: () => void;
}) {
  return (
    <div
      data-theme="cosmic"
      className={cn("birth-input-screen relative isolate min-h-screen overflow-hidden text-cream")}
    >
      <nav
        className={cn(
          "sticky top-0 z-50 border-b px-6 backdrop-blur-xl sm:px-10",
          "border-gold/20 bg-night/90"
        )}
      >
        <div className="mx-auto flex h-16 max-w-[1100px] items-center justify-between">
          <button
            className="border-0 bg-transparent text-[15px] font-bold uppercase tracking-[2px] text-cream"
            onClick={onBack}
          >
            Veda<span>Light</span>
          </button>
          {navControls}
        </div>
      </nav>

      <main className="relative z-10 min-h-[calc(100vh-64px)] px-5 py-9 sm:px-10 sm:py-14 lg:px-0">
        <section
          className={cn(
            "birth-input-form-panel mx-auto w-full rounded-[18px] border p-6 backdrop-blur-[26px] sm:p-10 lg:mx-0 lg:ml-12 xl:ml-[7vw]",
            "border-gold/25 bg-[rgba(16,12,22,0.44)] text-cream shadow-[0_30px_100px_rgba(0,0,0,0.50),0_0_60px_rgba(201,169,110,0.06),inset_0_1px_0_rgba(255,255,255,0.07)]",
            maxWidthClass
          )}
        >
          <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
            <button
              className="inline-flex items-center gap-1 border-0 bg-transparent text-sm text-cream/55 transition hover:text-cream"
              onClick={onBack}
            >
              <span aria-hidden>←</span> {backLabel}
            </button>
            <div className="flex flex-wrap items-center justify-end gap-2">{badge}</div>
          </div>

          {steps?.length ? (
            <div className="mb-12 flex items-start">
              {steps.map((step, index) => (
                <BirthInputProgressStep
                  key={`${step.index}:${step.label}`}
                  active={step.active}
                  label={step.label}
                  index={step.index}
                  last={index === steps.length - 1}
                />
              ))}
            </div>
          ) : null}

          <div className="mb-9 flex items-start gap-3.5">
            <div className="grid size-[38px] shrink-0 place-items-center rounded-[10px] border border-gold/30 bg-cream/10 text-gold shadow-[0_10px_28px_rgba(0,0,0,0.28)]">
              {icon}
            </div>
            <div>
              <h1 className="mb-1.5 text-[27px] font-light tracking-normal text-cream">{title}</h1>
              <p className="max-w-[520px] text-sm leading-relaxed text-cream/62">{subtitle}</p>
            </div>
          </div>

          {children}
        </section>
      </main>
    </div>
  );
}

function BirthInputProgressStep({
  active = false,
  label,
  index,
  last = false
}: {
  active?: boolean;
  label: string;
  index: number;
  last?: boolean;
}) {
  return (
    <div
      className={cn(
        "relative flex-1 text-center text-xs tracking-[0.3px]",
        active ? "text-gold-light" : "text-cream/42"
      )}
    >
      {!last && <div className="absolute left-[55%] right-[-55%] top-[15px] h-px bg-gold/25" />}
      <div
        className={cn(
          "relative z-[1] mx-auto mb-2 grid size-[30px] place-items-center rounded-full border text-[13px]",
          active ? "border-gold bg-gold text-white" : "border-gold/30 bg-white/5 text-cream/70"
        )}
      >
        {index}
      </div>
      {label}
    </div>
  );
}
