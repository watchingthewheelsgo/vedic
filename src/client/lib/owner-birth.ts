import { useEffect, useState } from "react";
import { api } from "../api";
import type { AdminSessionSummary, BirthTimePrecision } from "../../shared/domain";
import type { Profile } from "./profile";

export type OwnerBirth = {
  birthDate: Date;
  birthTime: Date | null;
  timePrecision: BirthTimePrecision;
  place: string;
  gender: string;
};

const PRECISIONS: BirthTimePrecision[] = ["exact", "approximate", "part_of_day", "unknown"];
const GENDERS: Record<string, string> = { female: "女", male: "男", 女: "女", 男: "男" };

/**
 * The account owner's birth details, from their own charts: the onboarding BaZi chart
 * (audience "self") first, else the newest chart with a birth date. Used to prefill new
 * readings; every field stays editable.
 */
export function ownerBirthFrom(sessions: AdminSessionSummary[]): OwnerBirth | null {
  const withBirth = sessions.filter((session) => session.subject?.birthDate);
  const subject = (
    withBirth.find((session) => session.subject?.relationship === "self") ?? withBirth[0]
  )?.subject;
  const date = subject?.birthDate?.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!subject || !date) return null;
  const birthDate = new Date(Number(date[1]), Number(date[2]) - 1, Number(date[3]));
  const precision = PRECISIONS.includes(subject.timePrecision as BirthTimePrecision)
    ? (subject.timePrecision as BirthTimePrecision)
    : subject.birthTime
      ? "exact"
      : "unknown";
  const time = subject.birthTime?.match(/^(\d{1,2}):(\d{2})/);
  const birthTime =
    time && precision !== "unknown"
      ? new Date(
          birthDate.getFullYear(),
          birthDate.getMonth(),
          birthDate.getDate(),
          Number(time[1]),
          Number(time[2])
        )
      : null;
  return {
    birthDate,
    birthTime,
    timePrecision: birthTime ? precision : "unknown",
    place: subject.birthPlace ?? "",
    gender: GENDERS[subject.gender ?? ""] ?? ""
  };
}

/** The onboarding profile as form values (it is the owner's own statement). */
export function ownerBirthFromProfile(profile: Profile): OwnerBirth | null {
  return ownerBirthFrom([
    {
      sessionId: "profile",
      status: "completed",
      stage: "profile",
      subject: {
        birthDate: profile.birthDate,
        birthTime: profile.birthTime,
        birthPlace: profile.birthPlace,
        timePrecision: profile.birthTime ? "exact" : "unknown",
        gender: profile.gender,
        relationship: "self"
      }
    } as AdminSessionSummary
  ]);
}

export function useOwnerBirth(): OwnerBirth | null {
  const [owner, setOwner] = useState<OwnerBirth | null>(null);
  useEffect(() => {
    let alive = true;
    // The profile first; owners from before onboarding fall back to their own charts.
    api
      .getProfile()
      .then((result) =>
        result.profile
          ? ownerBirthFromProfile(result.profile)
          : api.listMySessions().then((sessions) => ownerBirthFrom(sessions.sessions))
      )
      .then((found) => alive && setOwner(found))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);
  return owner;
}
