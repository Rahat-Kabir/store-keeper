import { useState } from 'react'
import {
  formatRelativeTime,
  getTicketPresentation,
  getTicketResultMessage,
} from '../ticketPresentation'
import type { TicketDetailResponse } from '../types'
import { StatusBadge } from './StatusBadge'

interface TicketDetailProps {
  ticket: TicketDetailResponse | null
  isLoading: boolean
  errorMessage: string | null
  hasTickets: boolean
  onCreateTicket: () => void
  onRetry: () => void
}

export function TicketDetail({
  ticket,
  isLoading,
  errorMessage,
  hasTickets,
  onCreateTicket,
  onRetry,
}: TicketDetailProps) {
  const [hasCopiedDraft, setHasCopiedDraft] = useState(false)

  if (isLoading) {
    return <p className="main-message">Loading ticket details…</p>
  }

  if (errorMessage) {
    return (
      <div className="main-message error-message" role="alert">
        <p>{errorMessage}</p>
        <button className="secondary-button" type="button" onClick={onRetry}>
          Try again
        </button>
      </div>
    )
  }

  if (!ticket) {
    return (
      <div className="welcome-state">
        <span className="eyebrow">Operator console</span>
        <h1>{hasTickets ? 'Select a ticket' : 'No tickets yet'}</h1>
        <p>
          {hasTickets
            ? 'Choose a ticket from the list to see its current graph state.'
            : 'Create the first ticket to run a customer request through Storekeeper.'}
        </p>
        {!hasTickets ? (
          <button className="primary-button" type="button" onClick={onCreateTicket}>
            Create a ticket
          </button>
        ) : null}
      </div>
    )
  }

  const presentation = getTicketPresentation(ticket, ticket)
  const resultMessage = getTicketResultMessage(ticket)
  const policyCitations = Array.from(
    new Set(ticket.task_results.flatMap((result) => result.policy_citations)),
  )

  const handleCopyDraft = async () => {
    if (!ticket.reply_draft) {
      return
    }
    await navigator.clipboard.writeText(ticket.reply_draft)
    setHasCopiedDraft(true)
    window.setTimeout(() => setHasCopiedDraft(false), 1800)
  }

  return (
    <article className="ticket-detail">
      <header className="detail-heading">
        <div className="ticket-title-row">
          <h1>{ticket.ticket_id}</h1>
          <StatusBadge label={presentation.label} tone={presentation.tone} />
        </div>
        <p>Received {formatRelativeTime(ticket.created_at)}</p>
      </header>

      <section className="content-card customer-message-card">
        <h2 className="card-label">Customer message</h2>
        <p>{ticket.ticket_text}</p>
      </section>

      {resultMessage ? (
        <div className={`result-banner result-banner-${presentation.tone}`}>
          {resultMessage}
        </div>
      ) : null}

      {ticket.status === 'pending_approval' ? (
        <section className="content-card pending-placeholder">
          <span className="card-label">Operator decision required</span>
          <p>
            The guarded workflow is paused safely. Approval details and decision controls
            arrive in Slice 8.3.
          </p>
        </section>
      ) : null}

      {ticket.reply_draft ? (
        <section className="content-card reply-card">
          <div className="reply-card-header">
            <h2 className="card-label">Drafted reply — not sent</h2>
            <button
              className="secondary-button copy-button"
              type="button"
              onClick={handleCopyDraft}
            >
              {hasCopiedDraft ? 'Copied' : 'Copy draft'}
            </button>
          </div>
          <div className="reply-copy">{ticket.reply_draft}</div>
          {policyCitations.length > 0 ? (
            <div className="citation-list">
              <span>Verified sources</span>
              <ul>
                {policyCitations.map((citation) => (
                  <li key={citation}>{citation}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <p className="draft-notice">
            Replies are always drafts. Copy this into your helpdesk or email; Storekeeper
            never messages customers directly.
          </p>
        </section>
      ) : null}
    </article>
  )
}
