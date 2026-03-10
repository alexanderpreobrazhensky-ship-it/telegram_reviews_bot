function createScheduler() {
  const tasks = [];
  return {
    schedule(task) {
      tasks.push(task);
      return task;
    },
    list() {
      return [...tasks];
    }
  };
}

module.exports = { createScheduler };
