import { useState } from "react";
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";

const HOURS = Array.from({ length: 24 }, (_, i) => i);
const ALL_MINUTES = Array.from({ length: 60 }, (_, i) => i);
const QUARTER_MINUTES = [0, 15, 30, 45];

export function BirthTimePicker({
  value,
  precision,
  invalid,
  onChange
}: {
  value: Date | null;
  precision: BirthTimePrecision;
  invalid: boolean;
  onChange: (date: Date | null) => void;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const disabled = precision === "unknown";
  const selectedHour = value?.getHours() ?? null;
  const selectedMinute = value ? normalizeMinuteForPrecision(value.getMinutes(), precision) : null;
  const minuteOptions =
    precision === "part_of_day" ? [0] : precision === "approximate" ? QUARTER_MINUTES : ALL_MINUTES;

  function commit(hour: number, minute: number) {
    onChange(makeBirthTime(hour, normalizeMinuteForPrecision(minute, precision)));
  }

  function selectHour(hour: number) {
    commit(hour, selectedMinute ?? 0);
    if (precision === "part_of_day") setOpen(false);
  }

  function selectMinute(minute: number) {
    commit(selectedHour ?? 0, minute);
    setOpen(false);
  }

  return (
    <div>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="lg"
            disabled={disabled}
            aria-invalid={invalid}
            className={cn(
              "w-full justify-start border-gold/30 bg-white px-4 text-left font-normal text-ink hover:border-gold/50 hover:bg-white data-[state=open]:border-gold data-[state=open]:ring-4 data-[state=open]:ring-gold/15",
              invalid && "border-red bg-red/5 hover:border-red"
            )}
          >
            <Clock3 className="size-4 shrink-0 text-gold-dim" />
            <span
              className={cn(
                "min-w-0 flex-1 text-[15px] font-medium tabular-nums",
                value ? "text-ink" : "text-muted"
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
          <PopoverContent className="w-[min(92vw,280px)] p-3" align="start">
            <div className="grid grid-cols-[1fr_auto_1fr] items-end gap-2">
              <TimeSelect
                title={t("time.hour")}
                values={HOURS}
                value={selectedHour}
                placeholder="HH"
                onSelect={selectHour}
              />
              <div className="pb-2 text-sm text-muted">:</div>
              <TimeSelect
                title={t("time.minute")}
                values={minuteOptions}
                value={precision === "part_of_day" ? 0 : selectedMinute}
                placeholder="MM"
                onSelect={selectMinute}
                disabled={precision === "part_of_day"}
              />
            </div>

            <div className="mt-3 flex items-center justify-between">
              <button
                type="button"
                className="text-xs text-muted transition hover:text-ink"
                onClick={() => {
                  onChange(null);
                  setOpen(false);
                }}
              >
                {t("common.clear")}
              </button>
              <Button type="button" size="sm" onClick={() => setOpen(false)}>
                {t("common.done")}
              </Button>
            </div>
          </PopoverContent>
        )}
      </Popover>
    </div>
  );
}

function TimeSelect({
  title,
  values,
  value,
  placeholder,
  disabled = false,
  onSelect
}: {
  title: string;
  values: number[];
  value: number | null;
  placeholder: string;
  disabled?: boolean;
  onSelect: (value: number) => void;
}) {
  return (
    <div>
      <div className="mb-1.5 text-[11px] text-muted">{title}</div>
      <Select
        value={value === null ? "" : String(value)}
        onValueChange={(next) => onSelect(Number(next))}
        disabled={disabled}
      >
        <SelectTrigger className="h-10 rounded-md px-3 text-sm tabular-nums">
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent className="max-h-64">
          {values.map((value) => {
            return (
              <SelectItem key={value} value={String(value)} className="tabular-nums">
                {padTimeUnit(value)}
              </SelectItem>
            );
          })}
        </SelectContent>
      </Select>
    </div>
  );
}
