import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { PlacePicker } from "../components/PlacePicker";
import type { BirthInput } from "../../shared/domain";

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"
];
const YEARS = Array.from({ length: 2010 - 1940 + 1 }, (_, i) => 2010 - i);
const DAYS = Array.from({ length: 31 }, (_, i) => i + 1);
const HOURS = Array.from({ length: 24 }, (_, i) => i);
const MINUTES = Array.from({ length: 60 }, (_, i) => i);

const pad = (n: number) => String(n).padStart(2, "0");

export function Intake() {
  const navigate = useNavigate();
  const [year, setYear] = useState("");
  const [month, setMonth] = useState("");
  const [day, setDay] = useState("");
  const [hour, setHour] = useState("");
  const [minute, setMinute] = useState("");
  const [place, setPlace] = useState("");
  const [name, setName] = useState("");
  const [gender, setGender] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onStart(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!year || !month || !day) return setError("Please select your full date of birth.");
    if (hour === "" || minute === "") return setError("Please select your birth time (hour and minute).");
    if (!place) return setError("Please choose your city of birth.");

    const monthNum = MONTHS.indexOf(month) + 1;
    const birth: BirthInput = {
      birthDate: `${year}-${pad(monthNum)}-${pad(Number(day))}`,
      birthTime: `${pad(Number(hour))}:${pad(Number(minute))}`,
      birthPlace: place,
      birthTimePrecision: "exact",
      gender: gender || "[not-collected]",
      relationship: "[not-collected]",
      timeSource: "web-form"
    };

    setBusy(true);
    try {
      const session = await api.createSkillSession(birth);
      await api.startCoreJob({ sessionId: session.sessionId, skill: "vedic-core", userMessage: "" });
      navigate(`/session/${session.sessionId}?tab=workshop`, {
        state: { name, birth }
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not start the report.");
      setBusy(false);
    }
  }

  return (
    <div className="form-screen-wrap">
      <div className="form-inner">
        <button className="back-btn" onClick={() => navigate("/")}>← Back</button>

        <div className="progress-steps">
          <div className="p-step active"><div className="p-dot">1</div>Birth Info</div>
          <div className="p-step"><div className="p-dot">2</div>Workshop</div>
          <div className="p-step"><div className="p-dot">3</div>Report</div>
        </div>

        <h2 className="form-h2">Enter Your Birth Details</h2>
        <p className="form-sub">Used solely to calculate your personalized chart</p>

        <div className="form-note">
          <strong>Why does birth time matter so much?</strong><br />
          Your birth time determines the Ascendant (Lagna) — the foundation of the entire chart. A 2-hour error can shift the Ascendant to a different sign. Check your birth certificate if possible.
        </div>

        <form onSubmit={onStart}>
          {error && <div className="form-error">{error}</div>}

          <div className="form-group">
            <label>Date of Birth</label>
            <div className="row-3">
              <select value={year} onChange={(e) => setYear(e.target.value)}>
                <option value="">Year</option>
                {YEARS.map((y) => <option key={y}>{y}</option>)}
              </select>
              <select value={month} onChange={(e) => setMonth(e.target.value)}>
                <option value="">Month</option>
                {MONTHS.map((m) => <option key={m}>{m}</option>)}
              </select>
              <select value={day} onChange={(e) => setDay(e.target.value)}>
                <option value="">Day</option>
                {DAYS.map((d) => <option key={d}>{d}</option>)}
              </select>
            </div>
          </div>

          <div className="form-group">
            <label>Time of Birth <span style={{ color: "var(--gold)" }}>*</span></label>
            <div className="row-2">
              <select value={hour} onChange={(e) => setHour(e.target.value)}>
                <option value="">Hour</option>
                {HOURS.map((h) => <option key={h} value={h}>{pad(h)}:00</option>)}
              </select>
              <select value={minute} onChange={(e) => setMinute(e.target.value)}>
                <option value="">Minute</option>
                {MINUTES.map((m) => <option key={m} value={m}>{pad(m)}</option>)}
              </select>
            </div>
            <div className="hint">Precise to the minute — check birth certificate or hospital records</div>
          </div>

          <PlacePicker value={place} onChange={setPlace} />

          <div className="form-group">
            <label>Your Name (optional)</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="How should the report address you?" />
          </div>

          <div className="form-group">
            <label>Gender</label>
            <select value={gender} onChange={(e) => setGender(e.target.value)}>
              <option value="">Select</option>
              <option value="Female">Female</option>
              <option value="Male">Male</option>
              <option value="Prefer not to say">Prefer not to say</option>
            </select>
            <div className="hint">Used for pronouns in the report — does not affect calculations</div>
          </div>

          <button className="btn btn-gold" style={{ width: "100%", padding: 15, fontSize: 15, marginTop: 8 }} disabled={busy}>
            {busy ? "Starting…" : "Start →"}
          </button>
        </form>
      </div>
    </div>
  );
}
