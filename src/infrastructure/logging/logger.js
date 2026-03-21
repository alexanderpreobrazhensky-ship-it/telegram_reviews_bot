function formatLog(level, message, meta = {}) {
  return {
    ts: new Date().toISOString(),
    level,
    message,
    ...meta
  };
}

function write(level, message, meta) {
  const payload = formatLog(level, message, meta);
  const line = JSON.stringify(payload);
  if (level === 'error') console.error(line);
  else if (level === 'warn') console.warn(line);
  else console.log(line);
}

const logger = {
  info(message, meta = {}) {
    write('info', message, meta);
  },
  warn(message, meta = {}) {
    write('warn', message, meta);
  },
  error(message, meta = {}) {
    write('error', message, meta);
  }
};

module.exports = logger;
