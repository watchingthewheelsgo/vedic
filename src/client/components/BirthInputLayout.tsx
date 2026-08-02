import type { ReactNode } from "react";
import { cn } from "../lib/cn";

type BirthInputStep = {
  label: string;
  index: number;
  active?: boolean;
  complete?: boolean;
};

export function BirthInputLayout({
  navControls,
  title,
  subtitle,
  icon,
  badge,
  steps,
  visual,
  maxWidthClass = "max-w-[500px]",
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
  visual?: ReactNode;
  maxWidthClass?: string;
  children: ReactNode;
  onBack: () => void;
}) {
  return (
    <div
      data-theme="cosmic"
      className={cn("birth-input-screen relative isolate min-h-screen overflow-x-clip text-cream")}
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
            Vedic<span>Dust</span>
          </button>
          {navControls}
        </div>
      </nav>

      <main className="relative z-10 min-h-[calc(100vh-64px)] px-5 py-5 sm:px-10 sm:py-6 xl:px-16">
        <div
          className={cn(
            "mx-auto w-full max-w-[1200px]",
            visual &&
              "lg:grid lg:grid-cols-[minmax(440px,500px)_minmax(0,620px)] lg:items-start lg:justify-center lg:gap-8"
          )}
        >
          <section
            className={cn(
              "birth-input-form-panel mx-auto w-full rounded-[18px] border p-5 backdrop-blur-[26px] sm:p-6 lg:mx-0 lg:min-h-[620px]",
              "border-gold/25 bg-[rgba(16,12,22,0.44)] text-cream shadow-[0_30px_100px_rgba(0,0,0,0.50),0_0_60px_rgba(201,169,110,0.06),inset_0_1px_0_rgba(255,255,255,0.07)]",
              maxWidthClass
            )}
          >
            {badge ? (
              <div className="mb-5 flex flex-wrap items-center justify-end gap-2">{badge}</div>
            ) : null}

            {steps?.length ? <BirthInputProgress steps={steps} /> : null}

            <div className="mb-6 flex items-start gap-3.5">
              <div className="grid size-[38px] shrink-0 place-items-center rounded-[10px] border border-gold/30 bg-cream/10 text-gold shadow-[0_10px_28px_rgba(0,0,0,0.28)]">
                {icon}
              </div>
              <div>
                <h1 className="mb-1 text-[25px] font-light tracking-normal text-cream">{title}</h1>
                <p className="max-w-[440px] text-[13px] leading-relaxed text-cream/55">
                  {subtitle}
                </p>
              </div>
            </div>

            {children}
          </section>
          {visual ? (
            <aside className="birth-input-visual sticky top-[88px] hidden w-full max-w-[560px] min-w-0 -translate-x-4 self-start lg:block">
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
    <div className="mb-5 px-0.5 py-1">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2" aria-hidden>
          {steps.map((step) => (
            <span
              key={step.index}
              className={cn(
                "size-1.5 rounded-full transition",
                step.active || step.complete ? "bg-gold" : "bg-cream/18"
              )}
            />
          ))}
        </div>
        <div className="text-xs text-cream/52">
          {activeStep.label} · {activeStep.index}/{steps.length}
        </div>
      </div>
      <div className="mt-2 h-0.5 overflow-hidden rounded-full bg-white/8">
        <div
          className="h-full rounded-full bg-gold transition-[width] duration-300"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
