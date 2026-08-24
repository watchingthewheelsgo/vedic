import * as React from "react";
import { format, type Locale } from "date-fns";
import { CalendarDays } from "lucide-react";
import { cn } from "../../lib/cn";
import { Button } from "./button";
import { Calendar } from "./calendar";
import { Popover, PopoverContent, PopoverTrigger } from "./popover";

type CalendarProps = React.ComponentProps<typeof Calendar>;

type DatePickerProps = {
  value: Date | null;
  onChange: (date: Date | null) => void;
  placeholder?: string;
  formatPattern?: string;
  locale?: Locale;
  invalid?: boolean;
  disabled?: CalendarProps["disabled"];
  startMonth?: CalendarProps["startMonth"];
  endMonth?: CalendarProps["endMonth"];
  className?: string;
};

export function DatePicker({
  value,
  onChange,
  placeholder = "Select date",
  formatPattern = "PPP",
  locale,
  invalid = false,
  disabled,
  startMonth,
  endMonth,
  className
}: DatePickerProps) {
  const [open, setOpen] = React.useState(false);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="lg"
          aria-invalid={invalid}
          className={cn(
            "birth-input-field-shell w-full justify-start border-white/12 bg-white/[0.035] px-4 text-left font-normal text-cream shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] hover:border-white/20 hover:bg-white/[0.055] data-[state=open]:border-gold/70 data-[state=open]:bg-white/[0.055] data-[state=open]:ring-2 data-[state=open]:ring-gold/15",
            invalid && "border-red bg-red/5 hover:border-red",
            className
          )}
        >
          <CalendarDays className="size-4 shrink-0 text-gold-dim" />
          <span className={cn("min-w-0 flex-1 truncate", value ? "text-cream" : "text-cream/40")}>
            {value ? format(value, formatPattern, { locale }) : placeholder}
          </span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-2" align="start">
        <Calendar
          mode="single"
          selected={value ?? undefined}
          onSelect={(date) => {
            onChange(date ?? null);
            setOpen(false);
          }}
          disabled={disabled}
          captionLayout="dropdown"
          startMonth={startMonth}
          endMonth={endMonth}
          locale={locale}
        />
      </PopoverContent>
    </Popover>
  );
}
