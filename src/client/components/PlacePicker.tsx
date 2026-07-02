import { useEffect, useRef, useState } from "react";
import { LoaderCircle, MapPin, Search } from "lucide-react";
import { api } from "../api";
import type { PlaceOption } from "../../shared/domain";

const isCoord = (s: string) => /lat\s*=/.test(s);

// Single-field city autocomplete (the pattern used by Google Places, booking
// sites, astrology apps): type a city → pick "City, Region, Country".
export function PlacePicker({
  value,
  onChange
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const [query, setQuery] = useState(value);
  const [options, setOptions] = useState<PlaceOption[]>([]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  const [loading, setLoading] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  // Debounced global search; skips when the text is already the committed value
  // or a raw coordinate string.
  useEffect(() => {
    const q = query.trim();
    if (q === value || q.length < 2 || isCoord(q)) {
      setOptions([]);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    const timer = window.setTimeout(() => {
      api
        .searchPlaces({ level: "city", q, limit: 8 }, controller.signal)
        .then((response) => {
          setOptions(response.options);
          setOpen(true);
          setHighlight(-1);
        })
        .catch(() => setOptions([]))
        .finally(() => setLoading(false));
    }, 250);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [query, value]);

  // Close the menu on outside click.
  useEffect(() => {
    function onDocClick(event: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  function commit(option: PlaceOption) {
    const picked = option.birthPlace ?? option.value;
    onChange(picked);
    setQuery(picked);
    setOptions([]);
    setOpen(false);
    setHighlight(-1);
  }

  function onInput(text: string) {
    setQuery(text);
    // Editing away from a committed selection clears it (forces a re-pick),
    // except raw coordinates which are valid as typed.
    if (isCoord(text)) {
      onChange(text.trim());
    } else if (value) {
      onChange("");
    }
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setHighlight((h) => Math.min(h + 1, options.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (event.key === "Enter") {
      if (highlight >= 0 && options[highlight]) {
        event.preventDefault();
        commit(options[highlight]);
      } else if (isCoord(query)) {
        event.preventDefault();
        onChange(query.trim());
        setOpen(false);
      }
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  const committed = Boolean(value) && query.trim() === value;

  return (
    <div className="form-group" ref={boxRef}>
      <label>City of Birth</label>
      <div className={`city-field ${committed ? "committed" : ""}`}>
        <MapPin size={16} />
        <input
          value={query}
          onChange={(event) => onInput(event.target.value)}
          onFocus={() => options.length && setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder="Type a city — e.g. Shanghai, London, New York"
          autoComplete="off"
          role="combobox"
          aria-expanded={open && options.length > 0}
          aria-controls="city-listbox"
          aria-autocomplete="list"
          aria-activedescendant={highlight >= 0 ? `city-opt-${highlight}` : undefined}
        />
        {loading ? <LoaderCircle size={15} className="city-spin" /> : <Search size={15} />}
        {open && options.length > 0 && (
          <ul className="city-menu" id="city-listbox" role="listbox">
            {options.map((option, index) => (
              <li
                key={option.id}
                id={`city-opt-${index}`}
                role="option"
                aria-selected={index === highlight}
                className={index === highlight ? "active" : ""}
                onMouseEnter={() => setHighlight(index)}
                onMouseDown={(event) => {
                  event.preventDefault();
                  commit(option);
                }}
              >
                <span className="city-name">{option.label}</span>
                <small>{option.meta}</small>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="hint">
        Worldwide search. No match? Paste coordinates:
        <code style={{ marginLeft: 6 }}>lat=34.05, lon=-118.24, tz=America/Los_Angeles</code>
      </div>
    </div>
  );
}
