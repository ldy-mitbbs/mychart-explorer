export function isOunces(unit: string | null | undefined): boolean {
  const u = (unit || '').trim().toLowerCase();
  return u === 'oz' || u === 'ounce' || u === 'ounces';
}

export function toDisplay(
  value: string,
  unit: string | null | undefined,
): { value: string; unit: string } {
  if (isOunces(unit)) {
    const n = parseFloat(value);
    if (!isNaN(n)) return { value: (n / 16).toFixed(1), unit: 'lb' };
  }
  return { value, unit: unit || '' };
}

const PRETTY_NAMES: Record<string, string> = {
  'WEIGHT/SCALE': 'Weight',
  'WEIGHT': 'Weight',
  'HEIGHT': 'Height',
  'R TEMPERATURE': 'Temperature',
  'TEMPERATURE': 'Temperature',
  'TEMP SOURCE': 'Temperature source',
  'R APACHE TEMPERATURE': 'Temperature (APACHE)',
  'R PULSE': 'Pulse',
  'PULSE': 'Pulse',
  'R HEART RATE': 'Heart rate',
  'HEART RATE': 'Heart rate',
  'R RESPIRATIONS': 'Respirations',
  'RESPIRATIONS': 'Respirations',
  'RESPIRATORY RATE': 'Respiratory rate',
  'R BLOOD PRESSURE': 'Blood pressure',
  'BLOOD PRESSURE': 'Blood pressure',
  'R BP LOCATION': 'BP location',
  'R BP CUFF SIZE': 'BP cuff size',
  'SYSTOLIC BP': 'Blood pressure (systolic)',
  'DIASTOLIC BP': 'Blood pressure (diastolic)',
  'R SPO2': 'Oxygen saturation (SpO₂)',
  'SPO2': 'Oxygen saturation (SpO₂)',
  'PULSE OXIMETRY': 'Oxygen saturation (SpO₂)',
  'R SAO2': 'Oxygen saturation (SaO₂)',
  'R BMI': 'BMI',
  'BMI': 'BMI',
  'R PAIN SCORE': 'Pain score',
  'PAIN SCORE': 'Pain score',
  'R HEAD CIRCUMFERENCE': 'Head circumference',
  'HEAD CIRCUMFERENCE': 'Head circumference',
  'R GLASGOW COMA SCALE SCORE': 'Glasgow Coma Scale',
};

export function prettyName(raw: string): string {
  if (!raw) return raw;
  const key = raw.trim().toUpperCase();
  if (PRETTY_NAMES[key]) return PRETTY_NAMES[key];
  const stripped = raw.replace(/^R\s+/i, '').replace(/_/g, ' ');
  return stripped
    .toLowerCase()
    .replace(/\b([a-z])/g, (c) => c.toUpperCase())
    .replace(/\bBp\b/g, 'BP')
    .replace(/\bBmi\b/g, 'BMI')
    .replace(/\bSpo2\b/gi, 'SpO₂')
    .replace(/\bSao2\b/gi, 'SaO₂');
}
