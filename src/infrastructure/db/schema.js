const schemaOverview = {
  clients: ['id', 'full_name', 'phone', 'email', 'telegram_id', 'preferred_channel', 'external_ids', 'source_system', 'source_of_truth', 'last_synced_at', 'local_pending_changes', 'needs_manual_review'],
  staff_users: ['id', 'telegram_id', 'full_name', 'role'],
  channel_accounts: ['id', 'client_id', 'channel', 'channel_user_id', 'username'],
  vehicles: ['id', 'client_id', 'vin', 'plate_number', 'brand', 'model', 'external_ids', 'source_system', 'source_of_truth', 'last_synced_at', 'local_pending_changes', 'needs_manual_review'],
  requests: ['id', 'client_id', 'vehicle_id', 'request_type', 'status', 'description', 'source_channel', 'assigned_master_id', 'lost_reason', 'external_ids', 'source_system', 'source_of_truth', 'last_synced_at', 'local_pending_changes', 'needs_manual_review'],
  request_status_history: ['id', 'request_id', 'from_status', 'to_status', 'changed_by', 'changed_by_role', 'reason', 'created_at'],
  request_internal_comments: ['id', 'request_id', 'actor_id', 'actor_role', 'text', 'created_at'],
  client_internal_notes: ['id', 'client_id', 'actor_id', 'actor_role', 'text', 'created_at'],
  visits: ['id', 'client_id', 'vehicle_id', 'request_id', 'status', 'is_repeat', 'is_warranty', 'is_promo', 'external_ids', 'source_system', 'source_of_truth', 'last_synced_at', 'local_pending_changes', 'needs_manual_review'],
  recommendations: ['id', 'client_id', 'vehicle_id', 'visit_id', 'status', 'severity', 'text', 'external_ids', 'source_system', 'source_of_truth', 'last_synced_at', 'local_pending_changes', 'needs_manual_review'],
  quality_cases: ['id', 'client_id', 'feedback_id', 'request_id', 'visit_id', 'status', 'assigned_to', 'reason_category'],
  quality_case_comments: ['id', 'quality_case_id', 'actor_id', 'actor_role', 'text', 'created_at'],
  communication_events: ['id', 'client_id', 'request_id', 'channel', 'direction', 'payload'],
  master_actions: ['id', 'actor_id', 'role', 'action', 'request_id', 'client_id', 'payload', 'created_at'],
  feedback: ['id', 'client_id', 'request_id', 'visit_id', 'rating', 'comment', 'source_channel', 'created_by', 'status', 'quality_case_id'],
  tasks: ['id', 'task_type', 'due_at', 'created_at', 'processed_at', 'status', 'attempt_count', 'last_error', 'payload'],
  integration_events: ['id', 'source_system', 'event_type', 'raw_payload', 'normalized_payload', 'processing_status', 'processing_attempt_count', 'last_error', 'created_at', 'processed_at', 'related_entity_type', 'related_entity_id', 'dedupe_key'],
  integration_event_logs: ['id', 'event_id', 'status', 'message', 'created_at']
};

module.exports = { schemaOverview };
