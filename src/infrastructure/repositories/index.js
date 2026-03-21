const { createRequestRepository } = require('./requestRepository');

function createRepositories({ db }) {
  return {
    requests: createRequestRepository({ db })
  };
}

module.exports = { createRepositories };
