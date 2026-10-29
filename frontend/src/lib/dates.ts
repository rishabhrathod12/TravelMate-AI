/**
 * Calendar dates are plain `YYYY-MM-DD` strings with no time zone. All maths is
 * done in UTC so a user's own time zone can never shift a date.
 */

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const MS_PER_DAY = 86_400_000;

export function parseIsoDate(value: string): Date | null {
  const match = ISO_DATE.exec(value);
  if (match === null) {
    return null;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  const isRealDate =
    date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
  return isRealDate ? date : null;
}

export function isValidIsoDate(value: string): boolean {
  return parseIsoDate(value) !== null;
}

function requireDate(value: string): Date {
  const date = parseIsoDate(value);
  if (date === null) {
    throw new RangeError(`Not a valid date: ${value}`);
  }
  return date;
}

/** Whole days from `startIso` to `endIso` (negative if the end is earlier). */
export function daysBetween(startIso: string, endIso: string): number {
  return Math.round((requireDate(endIso).getTime() - requireDate(startIso).getTime()) / MS_PER_DAY);
}

export function addDays(isoDate: string, days: number): string {
  const date = requireDate(isoDate);
  return new Date(date.getTime() + days * MS_PER_DAY).toISOString().slice(0, 10);
}

const DAY_FORMAT = new Intl.DateTimeFormat("en-GB", {
  weekday: "short",
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

const DATE_TIME_FORMAT = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
  timeZone: "UTC",
});

export function formatDay(isoDate: string): string {
  return DAY_FORMAT.format(requireDate(isoDate));
}

/** An ISO timestamp shown in UTC. The domain has no destination time zone yet. */
export function formatUtcDateTime(isoTimestamp: string): string {
  const time = Date.parse(isoTimestamp);
  if (Number.isNaN(time)) {
    return "Unknown time";
  }
  return `${DATE_TIME_FORMAT.format(time)} UTC`;
}

export function formatDuration(startIso: string, endIso: string): string {
  const minutes = Math.round((Date.parse(endIso) - Date.parse(startIso)) / 60_000);
  if (Number.isNaN(minutes) || minutes < 0) {
    return "Unknown duration";
  }
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return hours > 0 ? `${hours}h ${rest}m` : `${rest}m`;
}
