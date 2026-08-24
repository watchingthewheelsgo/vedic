import { useEffect, useRef, useState } from "react";
import { Clock3 } from "lucide-react";
import type { BirthTimePrecision } from "../../shared/domain";
import { useI18n } from "../i18n/provider";
import {
  formatTimeLabel,
  makeBirthTime,
  normalizeMinuteForPrecision,
  padTimeUnit
} from "../lib/birth-time";
import { cn } from "../lib/cn";
import { Button } from "./ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";

const HOURS = Array.from({ length: 24 }, (_, i) => i);
const ALL_MINUTES = Array.from({ length: 60 }, (_, i) => i);
const WHEEL_ITEM_HEIGHT = 42;

export function BirthTimePicker({
  value,
  precision,
  invalid,
  onChange,
  onPreviewChange
}: {
  value: Date | null;
  precision: BirthTimePrecision;
  invalid: boolean;
  onChange: (date: Date | null) => void;
  onPreviewChange?: (date: Date | null) => void;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const disabled = precision === "unknown";
  const selectedHour = value?.getHours() ?? null;
  const selectedMinute = value ? normalizeMinuteForPrecision(value.getMinutes(), precision) : null;
  const minuteOptions = precision === "part_of_day" ? [0] : ALL_MINUTES;
  const [draftHour, setDraftHour] = useState(selectedHour ?? 12);
  const [draftMinute, setDraftMinute] = useState(selectedMinute ?? 0);

  function changeOpen(nextOpen: boolean) {
    if (nextOpen) {
      const nextHour = selectedHour ?? 12;
      const nextMinute = selectedMinute ?? 0;
      setDraftHour(nextHour);
      setDraftMinute(nextMinute);
      onPreviewChange?.(
        makeBirthTime(nextHour, normalizeMinuteForPrecision(nextMinute, precision))
      );
    } else {
      onPreviewChange?.(value);
    }
    setOpen(nextOpen);
  }

  return (
    <div>
      <Popover open={open} onOpenChange={changeOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="lg"
            disabled={disabled}
            aria-invalid={invalid}
            className={cn(
              "birth-input-field-shell w-full justify-start border-white/12 bg-white/[0.035] px-4 text-left font-normal text-cream shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] hover:border-white/20 hover:bg-white/[0.055] data-[state=open]:border-gold/70 data-[state=open]:bg-white/[0.055] data-[state=open]:ring-2 data-[state=open]:ring-gold/15",
              invalid && "border-red bg-red/5 hover:border-red"
            )}
          >
            <Clock3 className="size-4 shrink-0 text-gold-dim" />
            <span
              className={cn(
                "min-w-0 flex-1 text-[15px] font-medium tabular-nums",
                value ? "text-cream" : "text-cream/40"
              )}
            >
              {disabled
                ? t("common.timeUnknown")
                : value
                  ? formatTimeLabel(value, precision)
                  : t("intake.time.select")}
            </span>
          </Button>
        </PopoverTrigger>

        {!disabled && (
          <PopoverContent className="w-[min(92vw,320px)] p-3" align="start">
            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
              <TimeWheel
                title={t("time.hour")}
                values={HOURS}
                value={draftHour}
                onSelect={(nextHour) => {
                  setDraftHour(nextHour);
                  onPreviewChange?.(
                    makeBirthTime(nextHour, normalizeMinuteForPrecision(draftMinute, precision))
                  );
                }}
              />
              <div className="pt-6 text-lg font-medium text-cream/32">:</div>
              <TimeWheel
                title={t("time.minute")}
                values={minuteOptions}
                value={precision === "part_of_day" ? 0 : draftMinute}
                onSelect={(nextMinute) => {
                  setDraftMinute(nextMinute);
                  onPreviewChange?.(
                    makeBirthTime(draftHour, normalizeMinuteForPrecision(nextMinute, precision))
                  );
                }}
                disabled={precision === "part_of_day"}
              />
            </div>

            <div className="mt-3 flex items-center justify-between">
              <button
                type="button"
                className="text-xs text-cream/50 transition hover:text-cream focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-gold/15"
                onClick={() => {
                  onPreviewChange?.(null);
                  onChange(null);
                  setOpen(false);
                }}
              >
                {t("common.clear")}
              </button>
              <Button
                type="button"
                size="sm"
                onClick={() => {
                  const nextValue = makeBirthTime(
                    draftHour,
                    normalizeMinuteForPrecision(draftMinute, precision)
                  );
                  onPreviewChange?.(nextValue);
                  onChange(nextValue);
                  setOpen(false);
                }}
              >
                {t("common.done")}
              </Button>
            </div>
          </PopoverContent>
        )}
      </Popover>
    </div>
  );
}

function TimeWheel({
  title,
  values,
  value,
  disabled = false,
  onSelect
}: {
  title: string;
  values: number[];
  value: number;
  disabled?: boolean;
  onSelect: (value: number) => void;
}) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const animationFrameRef = useRef<number | null>(null);
  const selectedIndex = Math.max(0, values.indexOf(value));

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const target = selectedIndex * WHEEL_ITEM_HEIGHT;
    if (Math.abs(viewport.scrollTop - target) > 1) viewport.scrollTop = target;
  }, [selectedIndex]);

  useEffect(
    () => () => {
      if (animationFrameRef.current !== null) {
        window.cancelAnimationFrame(animationFrameRef.current);
      }
    },
    []
  );

  function selectIndex(nextIndex: number, behavior: ScrollBehavior = "smooth") {
    const boundedIndex = Math.max(0, Math.min(values.length - 1, nextIndex));
    onSelect(values[boundedIndex]);
    viewportRef.current?.scrollTo({
      top: boundedIndex * WHEEL_ITEM_HEIGHT,
      behavior
    });
  }

  function handleScroll() {
    if (disabled || !viewportRef.current) return;
    if (animationFrameRef.current !== null) {
      window.cancelAnimationFrame(animationFrameRef.current);
    }
    animationFrameRef.current = window.requestAnimationFrame(() => {
      const nextIndex = Math.max(
        0,
        Math.min(values.length - 1, Math.round(viewportRef.current!.scrollTop / WHEEL_ITEM_HEIGHT))
      );
      if (values[nextIndex] !== value) onSelect(values[nextIndex]);
    });
  }

  return (
    <div className={cn("min-w-0", disabled && "opacity-45")}>
      <div className="mb-1.5 text-center text-[11px] font-medium text-muted">{title}</div>
      <div className="relative h-[210px] overflow-hidden rounded-[8px] border border-white/[0.08] bg-black/20">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-1 top-[84px] z-10 h-[42px] rounded-[6px] border-y border-gold/30 bg-gold/[0.07] shadow-[inset_0_1px_0_rgba(255,255,255,0.035)]"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 z-20 h-[72px] bg-gradient-to-b from-[#151312] to-transparent"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 bottom-0 z-20 h-[72px] bg-gradient-to-t from-[#151312] to-transparent"
        />
        <div
          ref={viewportRef}
          role="listbox"
          aria-label={title}
          aria-disabled={disabled}
          tabIndex={disabled ? -1 : 0}
          onScroll={handleScroll}
          onKeyDown={(event) => {
            if (disabled) return;
            if (event.key === "ArrowUp") {
              event.preventDefault();
              selectIndex(selectedIndex - 1);
            } else if (event.key === "ArrowDown") {
              event.preventDefault();
              selectIndex(selectedIndex + 1);
            } else if (event.key === "Home") {
              event.preventDefault();
              selectIndex(0);
            } else if (event.key === "End") {
              event.preventDefault();
              selectIndex(values.length - 1);
            }
          }}
          className={cn(
            "h-full snap-y snap-mandatory overflow-y-auto overscroll-contain py-[84px] outline-none [scrollbar-width:none] focus-visible:ring-4 focus-visible:ring-inset focus-visible:ring-gold/15 [&::-webkit-scrollbar]:hidden",
            disabled && "overflow-hidden"
          )}
        >
          {values.map((option, index) => (
            <button
              type="button"
              role="option"
              aria-selected={option === value}
              key={option}
              disabled={disabled}
              onClick={() => selectIndex(index)}
              className={cn(
                "flex h-[42px] w-full snap-center items-center justify-center text-base tabular-nums transition-[color,transform] focus-visible:outline-none",
                option === value
                  ? "scale-105 font-semibold text-cream"
                  : "text-cream/35 hover:text-cream/65"
              )}
            >
              {padTimeUnit(option)}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
