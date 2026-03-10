const schemaOverview = {
  clients: ['id', 'full_name', 'phone', 'email', 'telegram_id', 'preferred_channel', 'external_ids', 'source_of_truth'],
  staff_users: ['id', 'telegram_id', 'full_name', 'role'],
  channel_accounts: ['id', 'client_id', 'channel', 'channel_user_id', 'username'],
  vehicles: ['id', 'client_id', 'vin', 'plate_number', 'brand', 'model'],
  requests: ['id', 'client_id', 'vehicle_id', 'request_type', 'status', 'description', 'source_channel', 'assigned_master_id', 'lost_reason'],
  request_status_history: ['id', 'request_id', 'from_status', 'to_status', 'changed_by', 'changed_by_role', 'reason', 'created_at'],
  request_internal_comments: ['id', 'request_id', 'actor_id', 'actor_role', 'text', 'created_at'],
  client_internal_notes: ['id', 'client_id', 'actor_id', 'actor_role', 'text', 'created_at'],
  visits: ['id', 'client_id', 'vehicle_id', 'request_id', 'status', 'is_repeat', 'is_warranty', 'is_promo'],
  recommendations: ['id', 'client_id', 'vehicle_id', 'visit_id', 'status', 'severity', 'text'],
  quality_cases: ['id', 'request_id', 'visit_id', 'status', 'assigned_to'],
  quality_case_comments: ['id', 'quality_case_id', 'actor_id', 'actor_role', 'text', 'created_at'],
  communication_events: ['id', 'client_id', 'request_id', 'channel', 'direction', 'payload'],
  master_actions: ['id', 'actor_id', 'role', 'action', 'request_id', 'client_id', 'payload', 'created_at'],
  tasks: ['id', 'task_type', 'scheduled_at', 'status', 'payload'],
  integration_events: ['id', 'event_type', 'integration', 'aggregate_type', 'aggregate_id', 'status', 'payload']
};

module.exports = { schemaOverview };
