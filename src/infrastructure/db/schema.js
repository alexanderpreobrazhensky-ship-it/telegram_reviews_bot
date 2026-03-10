const schemaOverview = {
  clients: ['id', 'full_name', 'phone', 'email', 'external_ids', 'source_of_truth'],
  channel_accounts: ['id', 'client_id', 'channel', 'channel_user_id', 'username'],
  vehicles: ['id', 'client_id', 'vin', 'plate_number', 'brand', 'model'],
  requests: ['id', 'client_id', 'vehicle_id', 'request_type', 'status', 'description'],
  visits: ['id', 'client_id', 'vehicle_id', 'request_id', 'status', 'is_repeat', 'is_warranty', 'is_promo'],
  recommendations: ['id', 'client_id', 'vehicle_id', 'visit_id', 'status', 'severity', 'text'],
  part_requests: ['id', 'client_id', 'request_id', 'part_number', 'quantity', 'status'],
  feedback: ['id', 'client_id', 'request_id', 'visit_id', 'rating', 'comment'],
  quality_cases: ['id', 'request_id', 'visit_id', 'status', 'assigned_to'],
  communication_events: ['id', 'client_id', 'request_id', 'channel', 'direction', 'payload'],
  tasks: ['id', 'task_type', 'scheduled_at', 'status', 'payload'],
  integration_events: ['id', 'event_type', 'integration', 'aggregate_type', 'aggregate_id', 'status', 'payload']
};

module.exports = { schemaOverview };
