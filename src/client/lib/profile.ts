export type Profile = {
  birthDate: string;
  birthTime: string | null;
  birthPlace: string;
  placeLabel: string;
  timezone: string;
  gender: "女" | "男";
};

export type ProfileInput = Omit<Profile, "birthTime"> & { birthTime: string };

/** natalAvailable: the profile, or an existing self chart, gives a Day Master. */
export type ProfileResponse = { profile: Profile | null; natalAvailable: boolean };
