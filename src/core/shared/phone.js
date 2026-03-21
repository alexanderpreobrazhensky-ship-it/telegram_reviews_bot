function extractPhoneDigits(raw) {
  return String(raw || '').replace(/\D/g, '');
}

function normalizePhone10(raw) {
  const digits = extractPhoneDigits(raw);
  if (!digits) return '';
  if (digits.length === 10) return digits;
  if (digits.length === 11 && (digits.startsWith('7') || digits.startsWith('8'))) return digits.slice(1);
  return digits;
}

function isValidPhone10(raw) {
  return /^\d{10}$/.test(normalizePhone10(raw));
}

function resolvePhoneInput(body = {}) {
  const candidates = [
    body.phone,
    body.phoneNumber,
    body.nativeContact?.phone,
    body.nativeContact?.phoneNumber,
    body.contact?.phone,
    body.contact?.phoneNumber,
    body.telegramContact?.phone_number,
    body.maxContact?.phoneNumber
  ];
  for (const value of candidates) {
    const normalized = normalizePhone10(value);
    if (normalized) return normalized;
  }
  return '';
}

module.exports = {
  extractPhoneDigits,
  normalizePhone10,
  isValidPhone10,
  resolvePhoneInput
};
