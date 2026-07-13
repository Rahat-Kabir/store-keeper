export type TicketStatus = 'pending_approval' | 'resolved' | 'not_found'
export type TicketOutcome = 'resolved' | 'escalated_to_human'
export type TicketDecision = 'approve' | 'reject'
export type TaskOutcome =
  | 'executed'
  | 'rejected_by_human'
  | 'denied_by_policy'
  | 'answered'
  | 'failed'

export interface TicketSummary {
  ticket_id: string
  ticket_text: string
  created_at: string
  status: TicketStatus
}

export interface ShippingAddress {
  first_name: string | null
  last_name: string | null
  company: string | null
  address1: string | null
  address2: string | null
  city: string | null
  province: string | null
  zip: string | null
  country: string | null
  phone: string | null
}

export interface TicketTask {
  intent: 'cancel_order' | 'refund_request' | 'address_change' | 'policy_question' | 'other'
  order_reference: string | null
  requested_action: 'cancel_order' | 'issue_refund' | 'update_shipping_address' | null
  new_shipping_address: ShippingAddress | null
  confidence: number
}

export interface GateVerdict {
  passed: boolean
  rule: string
  reason: string
  flags: string[]
}

export interface TaskResult {
  task: TicketTask
  outcome: TaskOutcome
  gate_verdict: GateVerdict | null
  action_result: Record<string, unknown> | null
  policy_citations: string[]
}

export interface ApprovalPayload {
  question: string
  action: 'cancel_order' | 'issue_refund' | 'update_shipping_address'
  order: string
  requested_reference: string | null
  amount: string
  gate_rule: string
  gate_reason: string
  flags: string[]
  current_shipping_address: ShippingAddress | null
  new_shipping_address: ShippingAddress | null
}

export interface TicketDetailResponse extends TicketSummary {
  pending_approval: ApprovalPayload | null
  tasks: TicketTask[]
  task_results: TaskResult[]
  reply_draft: string | null
  ticket_outcome: TicketOutcome | null
  escalation_reason: string | null
}
