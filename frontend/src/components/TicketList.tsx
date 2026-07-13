import { useMemo, useState } from 'react'
import {
  formatRelativeTime,
  getApprovalActionHeadline,
  getHistoryStatusText,
  getTicketPresentation,
} from '../ticketPresentation'
import type { TicketDetailResponse, TicketSummary } from '../types'
import { StatusBadge } from './StatusBadge'

const INITIAL_HISTORY_COUNT = 15

interface TicketListProps {
  tickets: TicketSummary[]
  ticketDetailsById: Record<string, TicketDetailResponse>
  selectedTicketId: string | null
  isCreatingTicket: boolean
  isLoading: boolean
  errorMessage: string | null
  onCreateTicket: () => void
  onSelectTicket: (ticketId: string) => void
  onRetry: () => void
}

export function TicketList({
  tickets,
  ticketDetailsById,
  selectedTicketId,
  isCreatingTicket,
  isLoading,
  errorMessage,
  onCreateTicket,
  onSelectTicket,
  onRetry,
}: TicketListProps) {
  const [visibleHistoryCount, setVisibleHistoryCount] = useState(INITIAL_HISTORY_COUNT)
  const pendingTickets = useMemo(
    () => tickets.filter((ticket) => ticket.status === 'pending_approval'),
    [tickets],
  )
  const historyTickets = useMemo(
    () => tickets.filter((ticket) => ticket.status !== 'pending_approval'),
    [tickets],
  )
  const visibleHistoryTickets = historyTickets.slice(0, visibleHistoryCount)
  const olderHistoryCount = Math.max(historyTickets.length - visibleHistoryCount, 0)

  return (
    <aside className="ticket-sidebar" aria-label="Tickets">
      {errorMessage ? (
        <div className="sidebar-message error-message" role="alert">
          <p>{errorMessage}</p>
          <button className="text-button" type="button" onClick={onRetry}>
            Try again
          </button>
        </div>
      ) : null}

      {isLoading ? <p className="sidebar-message">Loading tickets…</p> : null}

      {!isLoading && !errorMessage && tickets.length === 0 ? (
        <div className="sidebar-message empty-sidebar">
          <p>No tickets yet.</p>
          <span>Create one to start the operator workflow.</span>
        </div>
      ) : null}

      {!isLoading && !errorMessage ? (
        <>
          <div className="ticket-zone-heading">
            <h1 className="section-label">
              Needs your approval ({pendingTickets.length})
            </h1>
            <button
              className="primary-button new-ticket-button"
              type="button"
              onClick={onCreateTicket}
            >
              <span aria-hidden="true">+</span> New ticket
            </button>
          </div>

          {pendingTickets.length === 0 ? (
            <div className="approval-empty-state">
              ✓ All caught up — nothing needs your approval.
            </div>
          ) : (
            <div className="pending-ticket-list">
              {pendingTickets.map((ticket) => {
                const ticketDetail = ticketDetailsById[ticket.ticket_id]
                const approval = ticketDetail?.pending_approval
                const isSelected =
                  !isCreatingTicket && ticket.ticket_id === selectedTicketId

                return (
                  <button
                    className={`pending-ticket-card${isSelected ? ' selected' : ''}`}
                    type="button"
                    key={ticket.ticket_id}
                    onClick={() => onSelectTicket(ticket.ticket_id)}
                    aria-current={isSelected ? 'true' : undefined}
                  >
                    <span className="pending-ticket-title-row">
                      <strong>
                        {approval
                          ? getApprovalActionHeadline(approval)
                          : 'Approval required'}
                      </strong>
                      <StatusBadge label="Pending" tone="attention" />
                    </span>
                    <span className="pending-ticket-preview">{ticket.ticket_text}</span>
                    <span className="pending-ticket-facts">
                      {approval ? (
                        <span className="amount-value">{approval.amount}</span>
                      ) : null}
                      <span>{formatRelativeTime(ticket.created_at)}</span>
                    </span>
                  </button>
                )
              })}
            </div>
          )}

          <h2 className="section-label history-heading">History</h2>
          <div className="history-ticket-list">
            {visibleHistoryTickets.map((ticket) => {
              const isSelected =
                !isCreatingTicket && ticket.ticket_id === selectedTicketId
              const ticketDetail = ticketDetailsById[ticket.ticket_id]
              const presentation = getTicketPresentation(ticket, ticketDetail)

              return (
                <button
                  className={`history-ticket-row${isSelected ? ' selected' : ''}`}
                  type="button"
                  key={ticket.ticket_id}
                  onClick={() => onSelectTicket(ticket.ticket_id)}
                  aria-current={isSelected ? 'true' : undefined}
                >
                  <span className="history-ticket-primary">
                    <span className="history-ticket-preview">{ticket.ticket_text}</span>
                    <span className="history-ticket-time">
                      {formatRelativeTime(ticket.created_at)}
                    </span>
                  </span>
                  <span className="history-ticket-secondary">
                    <span className={`history-status history-status-${presentation.tone}`}>
                      {getHistoryStatusText(presentation)}
                    </span>
                    <span className="history-ticket-id">{ticket.ticket_id}</span>
                  </span>
                </button>
              )
            })}
          </div>
          {olderHistoryCount > 0 ? (
            <button
              className="secondary-button load-more-button"
              type="button"
              onClick={() => setVisibleHistoryCount(historyTickets.length)}
            >
              Load more ({olderHistoryCount} older)
            </button>
          ) : null}
        </>
      ) : null}
    </aside>
  )
}
