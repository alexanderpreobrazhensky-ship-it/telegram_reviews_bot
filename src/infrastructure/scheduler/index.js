function createScheduler({ db, handlers = {}, logger = console, intervalMs = 15000, batchSize = 10, maxAttempts = 3, stuckTimeoutMs = 300000 } = {}) {
  let timer = null;
  let running = false;

  async function runOnce() {
    if (running || !db?.claimDueTasks) return { processed: 0 };
    running = true;
    let processed = 0;
    try {
      const dueTasks = db.claimDueTasks({ limit: batchSize, stuckTimeoutMs });
      for (const task of dueTasks) {
        const handler = handlers[task.taskType];
        if (!handler) {
          db.failTask(task.id, `NO_HANDLER:${task.taskType}`, 1);
          logger.warn?.(`scheduler no handler for ${task.taskType}`);
          continue;
        }

        try {
          await handler(task);
          db.completeTask(task.id);
          processed += 1;
        } catch (error) {
          db.failTask(task.id, error?.message || String(error), maxAttempts);
          logger.error?.(`scheduler task failed ${task.id}: ${error?.message || error}`);
        }
      }
    } finally {
      running = false;
    }
    return { processed };
  }

  function start() {
    if (timer) return;
    timer = setInterval(() => {
      runOnce().catch((error) => {
        logger.error?.(`scheduler loop failed: ${error?.message || error}`);
      });
    }, Math.max(1000, Number(intervalMs) || 15000));
  }

  function stop() {
    if (!timer) return;
    clearInterval(timer);
    timer = null;
  }

  return { start, stop, runOnce };
}

module.exports = { createScheduler };
