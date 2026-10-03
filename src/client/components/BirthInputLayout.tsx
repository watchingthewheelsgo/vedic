import type { ReactNode } from "react";
import { cn } from "../lib/cn";

type BirthInputStep = {
  label: string;
  index: number;
  active?: boolean;
  complete?: boolean;
};

export function BirthInputLayout({
  title,
  subtitle,
  icon,
  badge,
  steps,
  visual,
  maxWidthClass = "max-w-[560px]",
  children
}: {
  navControls: ReactNode;
  backLabel: string;
  title: string;
  subtitle: string;
  icon: ReactNode;
  badge?: ReactNode;
  steps?: BirthInputStep[];
  visual?: ReactNode;
  maxWidthClass?: string;
  children: ReactNode;
  onBack: () => void;
}) {
  return (
    <div
      data-theme="cosmic"
      className={cn("birth-input-screen relative isolate min-h-0 overflow-x-clip text-cream")}
    >
      <main className="relative z-10 min-h-0 px-4 py-5 sm:px-7 sm:py-7 xl:px-10">
        <div
          className={cn(
            "mx-auto w-full max-w-[1280px]",
            visual &&
              "birth-input-workspace overflow-hidden rounded-3xl border border-white/[0.08] bg-night-2 lg:grid lg:min-h-[calc(100dvh-3.5rem)] lg:grid-cols-[minmax(440px,0.92fr)_minmax(0,1.08fr)] lg:items-stretch"
          )}
        >
          <section
            className={cn(
              "birth-input-form-panel mx-auto flex w-full flex-col p-5 text-cream sm:p-8",
              visual
                ? "max-w-[680px] lg:max-w-none lg:border-r lg:border-white/[0.07] lg:px-10 lg:py-9 xl:px-12"
                : "rounded-3xl border border-white/[0.08] bg-night-2",
              !visual && maxWidthClass
            )}
          >
            {badge ? (
              <div className="mb-5 flex flex-wrap items-center justify-end gap-2">{badge}</div>
            ) : null}

            {steps?.length ? <BirthInputProgress steps={steps} /> : null}

            <div className="mb-7 flex items-start gap-3.5">
              <div className="mt-1 grid size-8 shrink-0 place-items-center text-gold-light/85">
                {icon}
              </div>
              <div>
                <h1 className="mb-1 font-display text-[34px] font-normal leading-tight text-cream">
                  {title}
                </h1>
                <p className="max-w-[470px] text-[13px] leading-relaxed text-cream/50">
                  {subtitle}
                </p>
              </div>
            </div>

            {children}
          </section>
          {visual ? (
            <aside className="birth-input-visual hidden w-full min-w-0 place-items-center bg-[radial-gradient(ellipse_70%_60%_at_50%_45%,rgba(244,162,89,0.07),transparent_70%)] bg-night lg:grid">
              {visual}
            </aside>
          ) : null}
        </div>
      </main>
    </div>
  );
}

function BirthInputProgress({ steps }: { steps: BirthInputStep[] }) {
  const foundActiveIndex = steps.findIndex((step) => step.active);
  const activeIndex = foundActiveIndex >= 0 ? foundActiveIndex : steps.length - 1;
  const activeStep = steps[activeIndex];
  const percent = Math.round(((activeIndex + 1) / steps.length) * 100);

  return (
    <div className="mb-7" aria-label={`${activeStep.label}, ${activeStep.index}/${steps.length}`}>
      <div className="grid grid-cols-3 gap-3">
        {steps.map((step) => (
          <div
            key={step.index}
            className={cn(
              "border-b pb-2.5 transition-colors",
              step.active ? "border-gold" : step.complete ? "border-gold/45" : "border-white/10"
            )}
          >
            <div
              className={cn(
                "mb-0.5 text-[10px] font-semibold tabular-nums",
                step.active || step.complete ? "text-gold-light/80" : "text-cream/28"
              )}
            >
              0{step.index}
            </div>
            <div
              className={cn(
                "truncate text-[11.5px] font-medium",
                step.active ? "text-cream" : step.complete ? "text-cream/58" : "text-cream/32"
              )}
            >
              {step.label}
            </div>
          </div>
        ))}
      </div>
      <div className="sr-only mt-2 h-0.5 overflow-hidden bg-white/8">
        <div
          className="h-full bg-gold origin-left transition-transform duration-200 ease-[cubic-bezier(0.23,1,0.32,1)]"
          style={{ transform: `scaleX(${percent / 100})` }}
        />
      </div>
    </div>
  );
}
