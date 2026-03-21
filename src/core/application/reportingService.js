function toDate(value) {
  const date = value ? new Date(value) : null;
  return Number.isNaN(date?.getTime?.()) ? null : date;
}

function safePct(part, total) {
  if (!total) return 0;
  return Number(((part / total) * 100).toFixed(2));
}

function buildPeriodBounds({ period, from, to, now = new Date() }) {
  if (from && to) {
    return { periodType: 'custom', periodStart: new Date(from), periodEnd: new Date(to) };
  }

  const end = new Date(now);
  if (period === 'monthly') {
    const start = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth(), 1));
    return { periodType: 'monthly', periodStart: start, periodEnd: end };
  }

  if (period === 'quarterly') {
    const quarterStartMonth = Math.floor(end.getUTCMonth() / 3) * 3;
    const start = new Date(Date.UTC(end.getUTCFullYear(), quarterStartMonth, 1));
    return { periodType: 'quarterly', periodStart: start, periodEnd: end };
  }

  const start = new Date(end);
  start.setUTCDate(end.getUTCDate() - 7);
  return { periodType: 'weekly', periodStart: start, periodEnd: end };
}

function filterRequests(store, filters) {
  const { periodStart, periodEnd, masterId, requestType, sourceChannel, sourceSystem } = filters;
  return store.requests.filter((item) => {
    const createdAt = toDate(item.createdAt);
    if (!createdAt || createdAt < periodStart || createdAt > periodEnd) return false;
    if (masterId && item.assignedMasterId !== masterId) return false;
    if (requestType && item.requestType !== requestType) return false;
    if (sourceChannel && item.sourceChannel !== sourceChannel) return false;
    if (sourceSystem && item.sourceSystem !== sourceSystem) return false;
    return true;
  });
}


function groupBy(items, keyFn) {
  return items.reduce((acc, item) => {
    const key = keyFn(item);
    if (!acc[key]) acc[key] = [];
    acc[key].push(item);
    return acc;
  }, {});
}

function avg(values) {
  if (!values.length) return 0;
  return Number((values.reduce((acc, item) => acc + item, 0) / values.length).toFixed(2));
}

function buildRequestsMetrics(store, filters) {
  const items = filterRequests(store, filters);
  const total = items.length;
  const byType = groupBy(items, (item) => item.requestType || 'unknown');
  const byStatus = groupBy(items, (item) => item.status || 'unknown');
  const bySourceChannel = groupBy(items, (item) => item.sourceChannel || 'unknown');
  const bySourceSystem = groupBy(items, (item) => item.sourceSystem || 'unknown');
  const processedCount = byStatus.done?.length || 0;
  const lostCount = byStatus.cancelled?.length || 0;
  const inProgressCount = (byStatus.assigned?.length || 0) + (byStatus.awaiting_client?.length || 0) + (byStatus.scheduled?.length || 0) + (byStatus.in_service?.length || 0);
  const archivedCount = 0;

  return {
    totalRequests: total,
    requestsByType: Object.fromEntries(Object.entries(byType).map(([key, value]) => [key, value.length])),
    requestsByStatus: Object.fromEntries(Object.entries(byStatus).map(([key, value]) => [key, value.length])),
    requestsBySourceChannel: Object.fromEntries(Object.entries(bySourceChannel).map(([key, value]) => [key, value.length])),
    requestsBySourceSystem: Object.fromEntries(Object.entries(bySourceSystem).map(([key, value]) => [key, value.length])),
    processedRequestsCount: processedCount,
    lostRequestsCount: lostCount,
    archivedRequestsCount: archivedCount,
    conversionLike: {
      processedShare: safePct(processedCount, total),
      lostShare: safePct(lostCount, total),
      inProgressShare: safePct(inProgressCount, total)
    }
  };
}

function buildFeedbackMetrics(store, filters) {
  const feedbackInRange = store.feedback.filter((item) => {
    const createdAt = toDate(item.createdAt);
    return createdAt && createdAt >= filters.periodStart && createdAt <= filters.periodEnd;
  });

  const totalFeedbackCount = feedbackInRange.length;
  const lowRatingCount = feedbackInRange.filter((item) => Number(item.rating) <= 2).length;
  return {
    totalFeedbackCount,
    averageRating: avg(feedbackInRange.map((item) => Number(item.rating || 0)).filter((item) => item > 0)),
    lowRatingCount,
    lowRatingShare: safePct(lowRatingCount, totalFeedbackCount)
  };
}

function buildQualityMetrics(store, filters) {
  const items = store.qualityCases.filter((item) => {
    const createdAt = toDate(item.createdAt);
    if (!createdAt || createdAt < filters.periodStart || createdAt > filters.periodEnd) return false;
    return !filters.masterId || item.assignedTo === filters.masterId;
  });
  const byStatus = groupBy(items, (item) => item.status || 'unknown');
  const resolvedCount = byStatus.resolved?.length || 0;
  const unresolvedCount = items.length - resolvedCount;
  return {
    qualityCaseCount: items.length,
    qualityCasesByStatus: Object.fromEntries(Object.entries(byStatus).map(([key, value]) => [key, value.length])),
    resolvedQualityCasesCount: resolvedCount,
    unresolvedQualityCasesCount: unresolvedCount
  };
}

function buildMasterMetrics(store, filters, requestsMetrics) {
  const touchedByMaster = {};
  for (const action of store.masterActions) {
    const createdAt = toDate(action.createdAt);
    if (!createdAt || createdAt < filters.periodStart || createdAt > filters.periodEnd) continue;
    if (!action.actorId || action.actorId === 'system') continue;
    touchedByMaster[action.actorId] = (touchedByMaster[action.actorId] || 0) + 1;
  }

  const requests = filterRequests(store, filters);
  const metrics = {};
  for (const request of requests) {
    const key = request.assignedMasterId || 'unassigned';
    if (!metrics[key]) {
      metrics[key] = {
        requestsTouched: touchedByMaster[key] || 0,
        processed: 0,
        lost: 0,
        qualityAssigned: 0,
        qualityResolved: 0
      };
    }
    if (request.status === 'done') metrics[key].processed += 1;
    if (request.status === 'cancelled') metrics[key].lost += 1;
  }

  for (const qualityCase of store.qualityCases) {
    const createdAt = toDate(qualityCase.createdAt);
    if (!createdAt || createdAt < filters.periodStart || createdAt > filters.periodEnd) continue;
    const key = qualityCase.assignedTo || 'unassigned';
    if (!metrics[key]) {
      metrics[key] = { requestsTouched: touchedByMaster[key] || 0, processed: 0, lost: 0, qualityAssigned: 0, qualityResolved: 0 };
    }
    metrics[key].qualityAssigned += 1;
    if (qualityCase.status === 'resolved') metrics[key].qualityResolved += 1;
  }

  return {
    masters: metrics,
    qualityTriggeredIssuesShareAmongFeedback: safePct(store.feedback.filter((f) => f.qualityCaseId).length, requestsMetrics.totalRequests || store.feedback.length)
  };
}

function normalizeSource(channel) {
  const known = new Set(['telegram_chat', 'webapp', 'max_chat', 'max_webapp', 'email', 'manual_import', 'one_c']);
  return known.has(channel) ? channel : 'other';
}

function buildSourceMetrics(store, filters) {
  const requests = filterRequests(store, filters);
  const sourceStats = { telegram_chat: 0, webapp: 0, max_chat: 0, max_webapp: 0, email: 0, manual_import: 0, one_c: 0, other: 0 };
  for (const request of requests) {
    sourceStats[normalizeSource(request.sourceChannel || request.sourceSystem)] += 1;
  }
  return sourceStats;
}

function buildRecommendationMetrics(store, filters) {
  const items = store.recommendations.filter((item) => {
    const createdAt = toDate(item.createdAt);
    return createdAt && createdAt >= filters.periodStart && createdAt <= filters.periodEnd;
  });
  const grouped = groupBy(items, (item) => item.status || 'unknown');
  return {
    totalRecommendations: items.length,
    actualRecommendations: grouped.actual?.length || 0,
    completedRecommendations: grouped.completed?.length || 0,
    declinedRecommendations: grouped.declined?.length || 0,
    expiredRecommendations: grouped.expired?.length || 0,
    criticalRecommendationsCount: items.filter((item) => item.severity === 'critical').length
  };
}

function buildTimingMetrics(store, filters) {
  const requests = filterRequests(store, filters);
  const historyByRequest = groupBy(store.requestStatusHistory, (item) => item.requestId);

  const firstMove = [];
  const toInProgress = [];
  const toProcessed = [];
  const toFeedbackTask = [];

  for (const request of requests) {
    const created = toDate(request.createdAt);
    if (!created) continue;
    const history = (historyByRequest[request.id] || []).sort((a, b) => String(a.createdAt).localeCompare(String(b.createdAt)));
    const firstNotNew = history.find((item) => item.toStatus && item.toStatus !== 'new');
    const inProgress = history.find((item) => item.toStatus === 'in_service');
    const processed = history.find((item) => item.toStatus === 'done');
    const feedbackTask = store.tasks.find((task) => task.taskType === 'feedback_request' && task.payload?.requestId === request.id);

    if (firstNotNew) firstMove.push((toDate(firstNotNew.createdAt) - created) / 60000);
    if (inProgress) toInProgress.push((toDate(inProgress.createdAt) - created) / 60000);
    if (processed) toProcessed.push((toDate(processed.createdAt) - created) / 60000);
    if (feedbackTask?.createdAt) toFeedbackTask.push((toDate(feedbackTask.createdAt) - created) / 60000);
  }

  return {
    avgMinutesToFirstMoveFromNew: avg(firstMove),
    avgMinutesToInProgress: avg(toInProgress),
    avgMinutesToProcessed: avg(toProcessed),
    avgMinutesToFeedbackTaskCreation: avg(toFeedbackTask)
  };
}

function formatSummaryText(summary) {
  return [
    `Сводка за период ${summary.period.periodType}: ${summary.period.periodStart} — ${summary.period.periodEnd}`,
    `Обращений: ${summary.requests.totalRequests}, обработано: ${summary.requests.processedRequestsCount}, потеряно: ${summary.requests.lostRequestsCount}`,
    `Feedback: ср.оценка ${summary.feedback.averageRating}, негативных кейсов ${summary.feedback.lowRatingCount}`,
    `Quality: открыто ${summary.quality.unresolvedQualityCasesCount}, решено ${summary.quality.resolvedQualityCasesCount}`,
    `Топ источники: ${summary.topSources.map((item) => `${item.source} (${item.count})`).join(', ') || 'нет данных'}`,
    `Ограничения данных: ${summary.dataLimitations.join('; ') || 'не выявлены'}`
  ].join('\n');
}

function buildManagementSummary({ store, filters }) {
  const requests = buildRequestsMetrics(store, filters);
  const feedback = buildFeedbackMetrics(store, filters);
  const quality = buildQualityMetrics(store, filters);
  const masters = buildMasterMetrics(store, filters, requests);
  const sources = buildSourceMetrics(store, filters);
  const recommendations = buildRecommendationMetrics(store, filters);
  const timing = buildTimingMetrics(store, filters);

  const topSources = Object.entries(sources)
    .map(([source, count]) => ({ source, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 3);

  const dataLimitations = [];
  if (!store.visits.length) dataLimitations.push('Пока нет полноценной воронки визитов (данные visits ограничены)');
  if (!store.integrationEvents.some((item) => item.sourceSystem === 'one_c')) dataLimitations.push('Нет полноценных one_c событий, отчёт строится по платформенным данным');

  const summary = {
    period: {
      periodType: filters.periodType,
      periodStart: filters.periodStart.toISOString(),
      periodEnd: filters.periodEnd.toISOString()
    },
    requests,
    feedback,
    quality,
    masters,
    sources,
    recommendations,
    timing,
    topSources,
    dataLimitations
  };

  return {
    summary,
    summaryText: formatSummaryText(summary)
  };
}

function createReportingService({ db }) {
  function resolveFilters(params = {}) {
    const bounds = buildPeriodBounds(params);
    return {
      ...bounds,
      masterId: params.masterId || null,
      requestType: params.requestType || null,
      sourceChannel: params.sourceChannel || null,
      sourceSystem: params.sourceSystem || null
    };
  }

  function buildPeriodicSnapshot({ reportType = 'management_summary', period = 'weekly', from, to, generatedBy = 'manual', notes = null, sourceDataVersion = null, filters = {} } = {}) {
    const store = db.readStore();
    const resolvedFilters = resolveFilters({ period, from, to, ...filters });
    const { summary, summaryText } = buildManagementSummary({ store, filters: resolvedFilters });
    return db.createReportSnapshot({
      reportType,
      periodType: resolvedFilters.periodType,
      periodStart: resolvedFilters.periodStart.toISOString(),
      periodEnd: resolvedFilters.periodEnd.toISOString(),
      metrics: summary,
      summaryText,
      generatedBy,
      sourceDataVersion,
      notes
    });
  }

  return {
    resolveFilters,
    buildRequestsMetrics: (params) => buildRequestsMetrics(db.readStore(), resolveFilters(params)),
    buildFeedbackMetrics: (params) => buildFeedbackMetrics(db.readStore(), resolveFilters(params)),
    buildQualityMetrics: (params) => buildQualityMetrics(db.readStore(), resolveFilters(params)),
    buildMasterMetrics: (params) => {
      const store = db.readStore();
      const filters = resolveFilters(params);
      const requests = buildRequestsMetrics(store, filters);
      return buildMasterMetrics(store, filters, requests);
    },
    buildSourceMetrics: (params) => buildSourceMetrics(db.readStore(), resolveFilters(params)),
    buildRecommendationMetrics: (params) => buildRecommendationMetrics(db.readStore(), resolveFilters(params)),
    buildManagementSummary: (params) => {
      const store = db.readStore();
      return buildManagementSummary({ store, filters: resolveFilters(params) });
    },
    buildPeriodicSnapshot,
    listSnapshots: ({ limit } = {}) => db.listReportSnapshots({ limit }),
    getSnapshotById: (id) => db.getReportSnapshotById(id)
  };
}

module.exports = {
  createReportingService,
  buildPeriodBounds,
  buildManagementSummary
};
