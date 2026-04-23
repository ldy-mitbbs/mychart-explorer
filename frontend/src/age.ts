// Compute full years between a FHIR `birthDate` (YYYY or YYYY-MM-DD) and today.
// Returns null when the input is missing or unparseable.
export function ageFromDob(dob: string | null | undefined): number | null {
  if (!dob) return null;
  const m = /^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?/.exec(dob);
  if (!m) return null;
  const y = Number(m[1]);
  const mo = m[2] ? Number(m[2]) - 1 : 0;
  const d = m[3] ? Number(m[3]) : 1;
  const birth = new Date(y, mo, d);
  if (Number.isNaN(birth.getTime())) return null;
  const now = new Date();
  let age = now.getFullYear() - birth.getFullYear();
  const md = now.getMonth() - birth.getMonth();
  if (md < 0 || (md === 0 && now.getDate() < birth.getDate())) age -= 1;
  return age >= 0 ? age : null;
}
