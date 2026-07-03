import * as React from "react";
import { format } from "date-fns";
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
  formatPattern = "MMMM d, yyyy",
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
            "w-full justify-start border-gold/30 bg-white px-4 text-left font-normal text-ink hover:border-gold/50 hover:bg-white data-[state=open]:border-gold data-[state=open]:ring-4 data-[state=open]:ring-gold/15",
            invalid && "border-red bg-red/5 hover:border-red",
            className
          )}
        >
          <CalendarDays className="size-4 shrink-0 text-gold-dim" />
          <span className={cn("min-w-0 flex-1 truncate", value ? "text-ink" : "text-muted")}>
            {value ? format(value, formatPattern) : placeholder}
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
        />
      </PopoverContent>
    </Popover>
  );
}
