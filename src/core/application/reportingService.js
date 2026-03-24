function toDate(value) {
  const date = value ? new Date(value) : null;
  return Number.isNaN(date?.getTime?.()) ? null : date;
}

function safePct(part, total) {
  if (!total) return 0;
  return Number(((part / total) * 100).toFixed(2));
}

function avg(values) {
  if (!values.length) return 0;
  return Number((values.reduce((acc, item) => acc + item, 0) / values.length).toFixed(2));
}

function sourceGroup(request = {}) {
  const provider = String(request.payload?.source_provider || request.sourceProvider || '').toLowerCase();
  if (provider === 't_business') return 't_business';
  const channel = String(request.sourceChannel || '').toLowerCase();
  if (channel.includes('telegram')) return 'telegram';
  if (channel.startsWith('max')) return 'max';
  if (channel.includes('webapp')) return 'webapp';
  if (channel.includes('email')) return 'email';
  return 'internal_manual';
}

function buildPeriodBounds({ period, from, to, now = new Date() }) {
  if (from && to) {
    return { periodType: 'custom', periodStart: new Date(from), periodEnd: new Date(to) };
  }

  const end = new Date(now);
  const todayStart = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth(), end.getUTCDate()));

  if (period === 'today') {
    return { periodType: 'today', periodStart: todayStart, periodEnd: end };
  }

  if (period === '7d' || period === 'weekly') {
    const start = new Date(todayStart);
    start.setUTCDate(start.getUTCDate() - 6);
    return { periodType: '7d', periodStart: start, periodEnd: end };
  }

  if (period === '30d') {
    const start = new Date(todayStart);
    start.setUTCDate(start.getUTCDate() - 29);
    return { periodType: '30d', periodStart: start, periodEnd: end };
  }

  if (period === 'monthly' || period === 'month') {
    const start = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth(), 1));
    return { periodType: 'monthly', periodStart: start, periodEnd: end };
  }

  if (period === 'quarterly' || period === 'quarter') {
    const quarterStartMonth = Math.floor(end.getUTCMonth() / 3) * 3;
    const start = new Date(Date.UTC(end.getUTCFullYear(), quarterStartMonth, 1));
    return { periodType: 'quarterly', periodStart: start, periodEnd: end };
  }

  if (period === 'all_time' || period === 'all') {
    return { periodType: 'all_time', periodStart: new Date('2000-01-01T00:00:00.000Z'), periodEnd: end };
  }

  const fallbackStart = new Date(todayStart);
  fallbackStart.setUTCDate(fallbackStart.getUTCDate() - 6);
  return { periodType: '7d', periodStart: fallbackStart, periodEnd: end };
}

function filterRequests(store, filters) {
  const {
    periodStart,
    periodEnd,
    masterId,
    requestType,
    sourceChannel,
    sourceProvider,
    status,
    substatus,
    existingClient,
    needsReview,
    isTBusiness
  } = filters;

  return store.requests.filter((item) => {
    const createdAt = toDate(item.createdAt);
    if (!createdAt || createdAt < periodStart || createdAt > periodEnd) return false;
    if (masterId && item.assignedMasterId !== masterId && item.assignedTo !== masterId) return false;
    if (requestType && item.requestType !== requestType) return false;
    if (sourceChannel && String(item.sourceChannel || '') !== sourceChannel) return false;
    if (sourceProvider && String(item.payload?.source_provider || '') !== sourceProvider) return false;
    if (status && item.status !== status) return false;
    if (substatus && item.substatus !== substatus) return false;

    const currentExisting = item.payload?.existing_client === true;
    const currentNeedsReview = item.payload?.needs_review === true;
    const currentTBusiness = String(item.payload?.source_provider || '') === 't_business' || String(item.sourceProvider || '') === 't_business';
    if (existingClient !== null && existingClient !== undefined && currentExisting !== Boolean(existingClient)) return false;
    if (needsReview !== null && needsReview !== undefined && currentNeedsReview !== Boolean(needsReview)) return false;
    if (isTBusiness !== null && isTBusiness !== undefined && currentTBusiness !== Boolean(isTBusiness)) return false;
    return true;
  });
}

function groupCount(items, keyFn) {
  return items.reduce((acc, item) => {
    const key = keyFn(item);
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}

function buildSummaryReport(store, filters) {
  const items = filterRequests(store, filters);
  const total = items.length;
  const counts = {
    total,
    new: items.filter((r) => r.status === 'new').length,
    in_progress: items.filter((r) => r.status === 'in_progress').length,
    processed: items.filter((r) => r.status === 'processed').length,
    in_service: items.filter((r) => r.status === 'in_service').length,
    completed: items.filter((r) => r.status === 'completed').length,
    rejected: items.filter((r) => r.substatus === 'rejected').length,
    spam: items.filter((r) => r.substatus === 'spam').length,
    waiting_decision: items.filter((r) => r.substatus === 'waiting_decision').length,
    needs_review: items.filter((r) => r.payload?.needs_review === true).length,
    existing_client: items.filter((r) => r.payload?.existing_client === true).length,
    new_client: items.filter((r) => r.payload?.existing_client !== true).length,
    t_business: items.filter((r) => String(r.payload?.source_provider || '') === 't_business').length
  };

  const toInProgressMinutes = [];
  const toCompletedMinutes = [];
  for (const request of items) {
    const created = toDate(request.createdAt);
    if (!created) continue;
    const assigned = toDate(request.assignedAt);
    const completed = toDate(request.completedAt);
    if (assigned) toInProgressMinutes.push((assigned - created) / 60000);
    if (completed) toCompletedMinutes.push((completed - created) / 60000);
  }

  return {
    period: {
      periodType: filters.periodType,
      periodStart: filters.periodStart.toISOString(),
      periodEnd: filters.periodEnd.toISOString()
    },
    counts,
    conversionToCompletedPct: safePct(counts.completed, total),
    avgMinutesToInProgress: avg(toInProgressMinutes),
    avgMinutesToCompleted: avg(toCompletedMinutes)
  };
}

function buildFunnelReport(store, filters) {
  const items = filterRequests(store, filters);
  const total = items.length;
  const stages = ['new', 'in_progress', 'processed', 'in_service', 'completed'];
  const stageCounts = Object.fromEntries(stages.map((stage) => [stage, items.filter((r) => r.status === stage).length]));
  const conversions = {
    new_to_in_progress_pct: safePct(stageCounts.in_progress + stageCounts.processed + stageCounts.in_service + stageCounts.completed, stageCounts.new || total),
    in_progress_to_processed_pct: safePct(stageCounts.processed + stageCounts.in_service + stageCounts.completed, stageCounts.in_progress || (stageCounts.in_progress + stageCounts.processed + stageCounts.in_service + stageCounts.completed)),
    processed_to_in_service_pct: safePct(stageCounts.in_service + stageCounts.completed, stageCounts.processed || (stageCounts.processed + stageCounts.in_service + stageCounts.completed)),
    in_service_to_completed_pct: safePct(stageCounts.completed, stageCounts.in_service || (stageCounts.in_service + stageCounts.completed))
  };
  return {
    period: { periodType: filters.periodType, periodStart: filters.periodStart.toISOString(), periodEnd: filters.periodEnd.toISOString() },
    total,
    stages: stageCounts,
    rejected: items.filter((r) => r.substatus === 'rejected').length,
    spam: items.filter((r) => r.substatus === 'spam').length,
    waiting_decision: items.filter((r) => r.substatus === 'waiting_decision').length,
    conversions
  };
}

function buildSourcesReport(store, filters) {
  const items = filterRequests(store, filters);
  const rows = ['telegram', 'max', 'webapp', 'email', 't_business', 'internal_manual'].map((source) => {
    const filtered = items.filter((r) => sourceGroup(r) === source);
    return {
      source,
      incoming: filtered.length,
      completed: filtered.filter((r) => r.status === 'completed').length,
      rejected: filtered.filter((r) => r.substatus === 'rejected').length,
      needs_review: filtered.filter((r) => r.payload?.needs_review === true).length,
      existing_client: filtered.filter((r) => r.payload?.existing_client === true).length
    };
  });
  return {
    period: { periodType: filters.periodType, periodStart: filters.periodStart.toISOString(), periodEnd: filters.periodEnd.toISOString() },
    rows
  };
}

function buildRejectionsReport(store, filters) {
  const items = filterRequests(store, { ...filters, substatus: 'rejected' });
  const byReason = groupCount(items, (r) => String(r.rejectionComment || r.lostReason || 'without_comment').slice(0, 100));
  const topReasons = Object.entries(byReason)
    .map(([reason, count]) => ({ reason, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 10);

  return {
    period: { periodType: filters.periodType, periodStart: filters.periodStart.toISOString(), periodEnd: filters.periodEnd.toISOString() },
    totalRejected: items.length,
    topReasons,
    items: items.slice(0, 200).map((r) => ({
      id: r.id,
      reason: r.rejectionComment || r.lostReason || '',
      source: sourceGroup(r),
      master: r.assignedTo || r.assignedMasterId || '',
      requestType: r.requestType || '',
      createdAt: r.createdAt
    }))
  };
}

function buildWarrantyReport(store, filters) {
  const items = filterRequests(store, filters).filter((r) => String(r.requestType || '').includes('warranty'));
  return {
    period: { periodType: filters.periodType, periodStart: filters.periodStart.toISOString(), periodEnd: filters.periodEnd.toISOString() },
    totalWarranty: items.length,
    processed: items.filter((r) => ['processed', 'in_service', 'completed'].includes(r.status)).length,
    completed: items.filter((r) => r.status === 'completed').length,
    stuck: items.filter((r) => ['new', 'in_progress', 'processed'].includes(r.status) && !r.archived).length,
    repeated: items.filter((r) => r.payload?.is_repeat_warranty === true).length,
    sources: groupCount(items, (r) => sourceGroup(r))
  };
}

function buildStuckReport(store, filters) {
  const items = filterRequests(store, filters);
  const now = filters.now || new Date();
  const newHours = filters.stuckNewHours || 24;
  const inProgressHours = filters.stuckInProgressHours || 48;
  const waitingDecisionHours = filters.stuckWaitingDecisionHours || 72;
  const needsReviewHours = filters.stuckNeedsReviewHours || 24;
  const toHours = (date) => (now - date) / 3600000;

  const longNew = items.filter((r) => r.status === 'new' && toHours(toDate(r.createdAt) || now) >= newHours);
  const longInProgress = items.filter((r) => r.status === 'in_progress' && toHours(toDate(r.assignedAt || r.createdAt) || now) >= inProgressHours);
  const longWaiting = items.filter((r) => r.status === 'processed' && r.substatus === 'waiting_decision' && toHours(toDate(r.updatedAt || r.createdAt) || now) >= waitingDecisionHours);
  const unresolvedNeedsReview = items.filter((r) => r.payload?.needs_review === true && r.status !== 'completed' && toHours(toDate(r.createdAt) || now) >= needsReviewHours);

  return {
    period: { periodType: filters.periodType, periodStart: filters.periodStart.toISOString(), periodEnd: filters.periodEnd.toISOString() },
    thresholdsHours: { new: newHours, in_progress: inProgressHours, waiting_decision: waitingDecisionHours, needs_review: needsReviewHours },
    long_new: longNew.length,
    long_in_progress: longInProgress.length,
    long_waiting_decision: longWaiting.length,
    unresolved_needs_review: unresolvedNeedsReview.length,
    samples: {
      new: longNew.slice(0, 20).map((r) => r.id),
      in_progress: longInProgress.slice(0, 20).map((r) => r.id),
      waiting_decision: longWaiting.slice(0, 20).map((r) => r.id),
      needs_review: unresolvedNeedsReview.slice(0, 20).map((r) => r.id)
    }
  };
}

function buildExistingVsNewReport(store, filters) {
  const items = filterRequests(store, filters);
  const existing = items.filter((r) => r.payload?.existing_client === true);
  const fresh = items.filter((r) => r.payload?.existing_client !== true);
  return {
    period: { periodType: filters.periodType, periodStart: filters.periodStart.toISOString(), periodEnd: filters.periodEnd.toISOString() },
    existing_count: existing.length,
    new_count: fresh.length,
    needs_review_count: items.filter((r) => r.payload?.needs_review === true).length,
    conversion_existing_completed_pct: safePct(existing.filter((r) => r.status === 'completed').length, existing.length),
    conversion_new_completed_pct: safePct(fresh.filter((r) => r.status === 'completed').length, fresh.length)
  };
}

function buildTBusinessReport(store, filters) {
  const items = filterRequests(store, filters).filter((r) => String(r.payload?.source_provider || '') === 't_business' || String(r.sourceProvider || '') === 't_business');
  const highPriority = items.filter((r) => String(r.payload?.priority || '').toLowerCase() === 'high' || String(r.priority || '').toLowerCase() === 'high');
  const target = highPriority.length ? highPriority : items;
  return {
    period: { periodType: filters.periodType, periodStart: filters.periodStart.toISOString(), periodEnd: filters.periodEnd.toISOString() },
    total: target.length,
    existing_client: target.filter((r) => r.payload?.existing_client === true).length,
    new_client: target.filter((r) => r.payload?.existing_client !== true).length,
    needs_review: target.filter((r) => r.payload?.needs_review === true).length,
    completed: target.filter((r) => r.status === 'completed').length,
    rejected: target.filter((r) => r.substatus === 'rejected').length,
    in_work: target.filter((r) => ['in_progress', 'processed', 'in_service'].includes(r.status)).length
  };
}

function buildFeedbackMetricsCompat(store, filters) {
  const items = (store.feedback || []).filter((item) => {
    const created = toDate(item.createdAt);
    return created && created >= filters.periodStart && created <= filters.periodEnd;
  });
  const low = items.filter((item) => Number(item.rating || 0) <= 2).length;
  return {
    totalFeedbackCount: items.length,
    averageRating: avg(items.map((item) => Number(item.rating || 0)).filter((value) => value > 0)),
    lowRatingCount: low,
    lowRatingShare: safePct(low, items.length)
  };
}

function buildQualityMetricsCompat(store, filters) {
  const items = (store.qualityCases || []).filter((item) => {
    const created = toDate(item.createdAt);
    return created && created >= filters.periodStart && created <= filters.periodEnd;
  });
  const byStatus = groupCount(items, (item) => item.status || 'unknown');
  const resolved = byStatus.resolved || 0;
  return {
    qualityCaseCount: items.length,
    qualityCasesByStatus: byStatus,
    resolvedQualityCasesCount: resolved,
    unresolvedQualityCasesCount: items.length - resolved
  };
}

function buildRecommendationMetricsCompat(store, filters) {
  const items = (store.recommendations || []).filter((item) => {
    const created = toDate(item.createdAt);
    return created && created >= filters.periodStart && created <= filters.periodEnd;
  });
  const byStatus = groupCount(items, (item) => item.status || 'unknown');
  return {
    totalRecommendations: items.length,
    actualRecommendations: byStatus.actual || 0,
    completedRecommendations: byStatus.completed || 0,
    declinedRecommendations: byStatus.declined || 0,
    expiredRecommendations: byStatus.expired || 0,
    criticalRecommendationsCount: items.filter((item) => item.severity === 'critical').length
  };
}

function formatSummaryText(summary) {
  const counts = summary.counts || {};
  return [
    `Сводка за период ${summary.period.periodType}: ${summary.period.periodStart} — ${summary.period.periodEnd}`,
    `Всего: ${counts.total || 0}; new=${counts.new || 0}; in_progress=${counts.in_progress || 0}; processed=${counts.processed || 0}; in_service=${counts.in_service || 0}; completed=${counts.completed || 0}`,
    `Отказы: ${counts.rejected || 0}; spam: ${counts.spam || 0}; waiting_decision: ${counts.waiting_decision || 0}`,
    `Existing/New: ${counts.existing_client || 0}/${counts.new_client || 0}; needs_review=${counts.needs_review || 0}; t_business=${counts.t_business || 0}`,
    `Конверсия в завершение: ${summary.conversionToCompletedPct}%`,
    `Среднее до взятия в работу: ${summary.avgMinutesToInProgress} мин`,
    `Среднее до завершения: ${summary.avgMinutesToCompleted} мин`
  ].join('\n');
}

function reportToCsvRows(reportType, report) {
  if (reportType === 'sources') return report.rows || [];
  if (reportType === 'rejections') return report.items || [];
  return [report];
}

function serializeRowsCsv(rows = []) {
  if (!rows.length) return 'no_data\n';
  const headers = Object.keys(rows[0]);
  const escape = (value) => {
    const raw = String(value ?? '');
    return /[",\n]/.test(raw) ? `"${raw.replace(/"/g, '""')}"` : raw;
  };
  return [headers.join(','), ...rows.map((row) => headers.map((h) => escape(row[h])).join(','))].join('\n');
}

function createReportingService({ db }) {
  function resolveFilters(params = {}) {
    const bounds = buildPeriodBounds(params);
    return {
      ...bounds,
      now: params.now ? new Date(params.now) : new Date(),
      masterId: params.masterId || null,
      requestType: params.requestType || null,
      sourceChannel: params.sourceChannel || null,
      sourceProvider: params.sourceProvider || null,
      status: params.status || null,
      substatus: params.substatus || null,
      existingClient: params.existingClient === undefined ? null : String(params.existingClient) === 'true',
      needsReview: params.needsReview === undefined ? null : String(params.needsReview) === 'true',
      isTBusiness: params.isTBusiness === undefined ? null : String(params.isTBusiness) === 'true',
      stuckNewHours: Number(params.stuckNewHours || 24),
      stuckInProgressHours: Number(params.stuckInProgressHours || 48),
      stuckWaitingDecisionHours: Number(params.stuckWaitingDecisionHours || 72),
      stuckNeedsReviewHours: Number(params.stuckNeedsReviewHours || 24)
    };
  }

  function buildReport(reportType, params = {}) {
    const store = db.readStore();
    const filters = resolveFilters(params);
    switch (reportType) {
      case 'summary': return buildSummaryReport(store, filters);
      case 'funnel': return buildFunnelReport(store, filters);
      case 'sources': return buildSourcesReport(store, filters);
      case 'rejections': return buildRejectionsReport(store, filters);
      case 'warranty': return buildWarrantyReport(store, filters);
      case 'stuck': return buildStuckReport(store, filters);
      case 'existing_new': return buildExistingVsNewReport(store, filters);
      case 't_business': return buildTBusinessReport(store, filters);
      default: return buildSummaryReport(store, filters);
    }
  }

  function buildManagementSummary(params = {}) {
    const summary = buildReport('summary', params);
    return { summary, summaryText: formatSummaryText(summary) };
  }

  function exportReportCsv({ reportType = 'summary', ...params } = {}) {
    const report = buildReport(reportType, params);
    return {
      reportType,
      report,
      csv: serializeRowsCsv(reportToCsvRows(reportType, report))
    };
  }

  function buildPeriodicSnapshot({ reportType = 'management_summary', period = 'weekly', from, to, generatedBy = 'manual', notes = null, sourceDataVersion = null, filters = {} } = {}) {
    const resolvedFilters = resolveFilters({ period, from, to, ...filters });
    const summaryPayload = buildManagementSummary({ period, from, to, ...filters });
    return db.createReportSnapshot({
      reportType,
      periodType: resolvedFilters.periodType,
      periodStart: resolvedFilters.periodStart.toISOString(),
      periodEnd: resolvedFilters.periodEnd.toISOString(),
      metrics: summaryPayload.summary,
      summaryText: summaryPayload.summaryText,
      generatedBy,
      sourceDataVersion,
      notes
    });
  }

  return {
    resolveFilters,
    buildReport,
    exportReportCsv,
    buildSummaryReport: (params) => buildReport('summary', params),
    buildFunnelReport: (params) => buildReport('funnel', params),
    buildSourcesReport: (params) => buildReport('sources', params),
    buildRejectionsReport: (params) => buildReport('rejections', params),
    buildWarrantyReport: (params) => buildReport('warranty', params),
    buildStuckReport: (params) => buildReport('stuck', params),
    buildExistingVsNewReport: (params) => buildReport('existing_new', params),
    buildTBusinessReport: (params) => buildReport('t_business', params),
    buildRequestsMetrics: (params) => {
      const report = buildReport('summary', params);
      return {
        totalRequests: report.counts.total,
        requestsByStatus: {
          new: report.counts.new,
          in_progress: report.counts.in_progress,
          processed: report.counts.processed,
          in_service: report.counts.in_service,
          completed: report.counts.completed
        },
        processedRequestsCount: report.counts.processed + report.counts.completed,
        lostRequestsCount: report.counts.rejected + report.counts.spam,
        archivedRequestsCount: report.counts.rejected + report.counts.spam + report.counts.completed,
        conversionLike: {
          processedShare: safePct(report.counts.processed + report.counts.completed, report.counts.total),
          lostShare: safePct(report.counts.rejected + report.counts.spam, report.counts.total),
          inProgressShare: safePct(report.counts.in_progress + report.counts.processed + report.counts.in_service, report.counts.total)
        }
      };
    },
    buildFeedbackMetrics: (params) => buildFeedbackMetricsCompat(db.readStore(), resolveFilters(params)),
    buildQualityMetrics: (params) => buildQualityMetricsCompat(db.readStore(), resolveFilters(params)),
    buildMasterMetrics: () => ({ masters: {}, qualityTriggeredIssuesShareAmongFeedback: 0 }),
    buildSourceMetrics: (params) => {
      const rows = buildReport('sources', params).rows;
      return rows.reduce((acc, row) => ({ ...acc, [row.source]: row.incoming }), {});
    },
    buildRecommendationMetrics: (params) => buildRecommendationMetricsCompat(db.readStore(), resolveFilters(params)),
    buildManagementSummary,
    buildPeriodicSnapshot,
    listSnapshots: ({ limit } = {}) => db.listReportSnapshots({ limit }),
    getSnapshotById: (id) => db.getReportSnapshotById(id)
  };
}

module.exports = {
  createReportingService,
  buildPeriodBounds
};
