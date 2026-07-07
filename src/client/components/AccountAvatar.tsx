import { UserRound } from "lucide-react";
import { cn } from "../lib/cn";

type AccountAvatarSize = "sm" | "md" | "lg" | "xl";

const sizeClass: Record<AccountAvatarSize, string> = {
  sm: "size-8 text-[11px]",
  md: "size-11 text-sm",
  lg: "size-14 text-base",
  xl: "size-16 text-lg"
};

const iconSize: Record<AccountAvatarSize, number> = {
  sm: 14,
  md: 17,
  lg: 21,
  xl: 24
};

export function AccountAvatar({
  imageUrl,
  initials,
  size = "md",
  showStatus = false,
  className
}: {
  imageUrl?: string;
  initials: string;
  size?: AccountAvatarSize;
  showStatus?: boolean;
  className?: string;
}) {
  const normalizedInitials = initials.trim().slice(0, 2).toUpperCase();

  return (
    <span
      className={cn(
        "relative grid shrink-0 place-items-center rounded-full bg-[linear-gradient(135deg,#f8e7b8_0%,#c9a96e_46%,#6c4c24_100%)] p-[1.5px] shadow-[0_10px_24px_rgba(44,31,15,0.18)]",
        sizeClass[size],
        className
      )}
    >
      <span className="grid h-full w-full place-items-center overflow-hidden rounded-full bg-night text-center font-semibold uppercase leading-none tracking-normal text-gold">
        {imageUrl ? (
          <img src={imageUrl} alt="" className="h-full w-full object-cover" />
        ) : normalizedInitials ? (
          normalizedInitials
        ) : (
          <UserRound size={iconSize[size]} strokeWidth={1.8} />
        )}
      </span>
      {showStatus && (
        <span className="absolute bottom-0 right-0 size-3.5 rounded-full border-2 border-cream bg-green shadow-[0_2px_8px_rgba(15,12,9,0.22)]" />
      )}
    </span>
  );
}
