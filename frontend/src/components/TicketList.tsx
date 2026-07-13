import {
  formatRelativeTime,
  getTicketPresentation,
} from '../ticketPresentation'
import type { TicketDetailResponse, TicketSummary } from '../types'
import { StatusBadge } from './StatusBadge'

interface TicketListProps {
  tickets: TicketSummary[]
  selectedTicket: TicketDetailResponse | null
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
  selectedTicket,
  selectedTicketId,
  isCreatingTicket,
  isLoading,
  errorMessage,
  onCreateTicket,
  onSelectTicket,
  onRetry,
}: TicketListProps) {
  return (
    <aside className="ticket-sidebar" aria-label="Tickets">
      <div className="ticket-list-header">
        <h1 className="section-label">Tickets</h1>
        <button className="secondary-button" type="button" onClick={onCreateTicket}>
          <span aria-hidden="true">+</span> New ticket
        </button>
      </div>

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

      <div className="ticket-list">
        {tickets.map((ticket) => {
          const isSelected = !isCreatingTicket && ticket.ticket_id === selectedTicketId
          const selectedDetail =
            selectedTicket?.ticket_id === ticket.ticket_id ? selectedTicket : null
          const presentation = getTicketPresentation(ticket, selectedDetail)

          return (
            <button
              className={`ticket-list-item${isSelected ? ' selected' : ''}`}
              type="button"
              key={ticket.ticket_id}
              onClick={() => onSelectTicket(ticket.ticket_id)}
              aria-current={isSelected ? 'true' : undefined}
            >
              <span className="ticket-list-meta">
                <span className="ticket-id">{ticket.ticket_id}</span>
                <StatusBadge label={presentation.label} tone={presentation.tone} />
              </span>
              <span className="ticket-preview">{ticket.ticket_text}</span>
              <span className="ticket-time">{formatRelativeTime(ticket.created_at)}</span>
            </button>
          )
        })}
      </div>
    </aside>
  )
}
