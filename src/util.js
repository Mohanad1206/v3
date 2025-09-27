
// util.js - helper functions
export function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

export function normalizeCurrency(cur) {
  if (!cur) return null;
  const t = cur.toString().trim().upperCase?.() || cur.toString().trim().toUpperCase();
  if (t in {"EGP":1,"USD":1,"EUR":1,"GBP":1,"SAR":1,"AED":1}) return t;
  // Heuristics
  if (/[₤£]/.test(cur)) return "GBP";
  if (/ج\.?م|EGP|E£| جنيه/.test(cur)) return "EGP";
  if (/\$/.test(cur)) return "USD";
  return null;
}

export function extractNumber(str) {
  if (str == null) return null;
  const cleaned = String(str).replace(/[^\d.,]/g, "").replace(/,/g, "");
  const m = cleaned.match(/\d+(\.\d+)?/);
  return m ? Number(m[0]) : null;
}

export function domainFromUrl(u) {
  try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return ""; }
}

export function nowIso() { return new Date().toISOString(); }
