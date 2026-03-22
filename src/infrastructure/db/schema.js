const schemaOverview = {
  clients: ['id', 'full_name', 'phone', 'telegram_id', 'max_id', 'preferred_channel', 'created_at', 'updated_at', 'data'],
  vehicles: ['id', 'client_id', 'vin', 'plate_number', 'brand', 'model', 'year', 'created_at', 'updated_at', 'data'],
  requests: ['id', 'client_id', 'vehicle_id', 'request_type', 'status', 'substatus', 'description', 'source_channel', 'assigned_master_id', 'assigned_to', 'assigned_at', 'assigned_by', 'archived', 'last_followup_at', 'lost_reason', 'created_at', 'updated_at', 'data'],
  request_events: ['id', 'event_scope', 'event_type', 'type', 'payload', 'request_id', 'client_id', 'quality_case_id', 'actor_id', 'actor_role', 'old_value', 'new_value', 'actor_type', 'comment', 'meta_json', 'created_at', 'data', 'parent_event_id'],
  communications: ['id', 'client_id', 'request_id', 'source', 'channel', 'direction', 'created_at', 'data'],
  tasks: ['id', 'task_type', 'status', 'due_at', 'created_at', 'processed_at', 'attempt_count', 'last_error', 'processing_started_at', 'updated_at', 'payload', 'data'],
  staff_users: ['id', 'telegram_id', 'max_id', 'full_name', 'role', 'created_at', 'updated_at', 'data'],
  quality_cases: ['id', 'client_id', 'feedback_id', 'request_id', 'visit_id', 'status', 'assigned_to', 'reason_category', 'summary', 'created_at', 'updated_at', 'data'],
  analytics_events: ['id', 'parent_event_id', 'event_type', 'channel', 'platform', 'request_type', 'request_id', 'client_id', 'status', 'meta_json', 'source_system', 'processing_status', 'related_entity_type', 'related_entity_id', 'dedupe_key', 'created_at', 'processed_at', 'data'],
  recommendations: ['id', 'client_id', 'visit_id', 'status', 'severity', 'interested', 'created_at', 'updated_at', 'data'],
  feedback: ['id', 'client_id', 'request_id', 'visit_id', 'rating', 'source_channel', 'created_by', 'status', 'quality_case_id', 'created_at', 'data'],
  report_snapshots: ['id', 'report_type', 'period_type', 'period_start', 'period_end', 'generated_at', 'generated_by', 'source_data_version', 'data'],
  meta: ['key', 'value']
};

module.exports = { schemaOverview };
