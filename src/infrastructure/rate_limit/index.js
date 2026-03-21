function createRateLimiter({ windowMs = 10000, limit = 10 } = {}) {
  const buckets = new Map();

  function prune(now) {
    for (const [key, bucket] of buckets.entries()) {
      bucket.hits = bucket.hits.filter((ts) => now - ts < windowMs);
      if (!bucket.hits.length) buckets.delete(key);
    }
  }

  return {
    consume(key) {
      const now = Date.now();
      prune(now);
      const bucket = buckets.get(key) || { hits: [] };
      bucket.hits = bucket.hits.filter((ts) => now - ts < windowMs);
      if (bucket.hits.length >= limit) {
        buckets.set(key, bucket);
        const retryAfterMs = Math.max(0, windowMs - (now - bucket.hits[0]));
        return { ok: false, retryAfterMs, remaining: 0, limit, windowMs };
      }
      bucket.hits.push(now);
      buckets.set(key, bucket);
      return { ok: true, retryAfterMs: 0, remaining: Math.max(0, limit - bucket.hits.length), limit, windowMs };
    }
  };
}

module.exports = { createRateLimiter };
