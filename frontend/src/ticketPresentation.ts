import type { TicketDetailResponse, TicketSummary } from './types'

export type StatusTone = 'neutral' | 'success' | 'danger' | 'attention'

export interface TicketPresentation {
  label: string
  tone: StatusTone
}

export function getTicketPresentation(
  ticket: TicketSummary,
  ticketDetail?: TicketDetailResponse | null,
): TicketPresentation {
  if (ticket.status === 'pending_approval') {
    return { label: 'Awaiting approval', tone: 'attention' }
  }

  if (ticketDetail?.ticket_outcome === 'escalated_to_human') {
    return { label: 'Escalated to you', tone: 'neutral' }
  }

  const taskOutcomes = ticketDetail?.task_results.map((result) => result.outcome) ?? []
  if (taskOutcomes.includes('rejected_by_human')) {
    return { label: 'Rejected', tone: 'neutral' }
  }
  if (taskOutcomes.includes('denied_by_policy')) {
    return { label: 'Denied by policy', tone: 'danger' }
  }
  if (taskOutcomes.includes('failed')) {
    return { label: 'Needs attention', tone: 'danger' }
  }
  if (taskOutcomes.includes('executed')) {
    return { label: 'Executed', tone: 'success' }
  }
  if (taskOutcomes.includes('answered')) {
    return { label: 'Answered', tone: 'success' }
  }
  return { label: 'Resolved', tone: 'neutral' }
}

export function getTicketResultMessage(ticket: TicketDetailResponse): string | null {
  if (ticket.status === 'pending_approval') {
    return 'This action is waiting for an operator decision.'
  }
  if (ticket.ticket_outcome === 'escalated_to_human') {
    return ticket.escalation_reason ?? 'This ticket needs manual follow-up.'
  }

  const taskOutcomes = ticket.task_results.map((result) => result.outcome)
  if (taskOutcomes.includes('rejected_by_human')) {
    return 'You rejected this action. No changes were made to the order.'
  }
  if (taskOutcomes.includes('denied_by_policy')) {
    const deniedResult = ticket.task_results.find(
      (result) => result.outcome === 'denied_by_policy',
    )
    return deniedResult?.gate_verdict?.reason ?? 'The request was denied by policy.'
  }
  if (taskOutcomes.includes('failed')) {
    return 'The requested action could not be completed and needs manual follow-up.'
  }
  if (taskOutcomes.includes('executed')) {
    return 'The approved action was completed successfully.'
  }
  if (taskOutcomes.includes('answered')) {
    return 'The policy question was answered from the verified sources below.'
  }
  return null
}

export function formatRelativeTime(dateValue: string): string {
  const timestamp = new Date(dateValue).getTime()
  if (Number.isNaN(timestamp)) {
    return dateValue
  }

  const elapsedSeconds = Math.round((timestamp - Date.now()) / 1000)
  const formatter = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
  const relativeUnits: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ['year', 31_536_000],
    ['month', 2_592_000],
    ['week', 604_800],
    ['day', 86_400],
    ['hour', 3_600],
    ['minute', 60],
  ]

  for (const [unit, secondsInUnit] of relativeUnits) {
    if (Math.abs(elapsedSeconds) >= secondsInUnit) {
      return formatter.format(Math.round(elapsedSeconds / secondsInUnit), unit)
    }
  }
  return 'just now'
}
