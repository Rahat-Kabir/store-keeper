import type {
  ApprovalPayload,
  ShippingAddress,
  TicketDecision,
} from '../types'

interface ApprovalCardProps {
  approval: ApprovalPayload
  activeDecision: TicketDecision | null
  errorMessage: string | null
  onDecide: (decision: TicketDecision) => void
  onRefresh: () => void
}

const ACTION_LABELS: Record<ApprovalPayload['action'], string> = {
  cancel_order: 'Cancel order',
  issue_refund: 'Issue full refund',
  update_shipping_address: 'Update shipping address',
}

export function ApprovalCard({
  approval,
  activeDecision,
  errorMessage,
  onDecide,
  onRefresh,
}: ApprovalCardProps) {
  const approveButtonLabel = getApproveButtonLabel(approval)
  const isSubmittingDecision = activeDecision !== null

  return (
    <section className="content-card approval-card" aria-labelledby="approval-heading">
      <div className="approval-card-heading">
        <div>
          <span className="eyebrow">Operator decision required</span>
          <h2 id="approval-heading">Review this Shopify action</h2>
        </div>
        <span className="approval-paused-label">Workflow paused</span>
      </div>

      <p className="approval-question">{approval.question}</p>

      <div className="order-binding" aria-label="Order reference verification">
        <div>
          <span>Customer wrote</span>
          <strong>{approval.requested_reference ?? 'No reference provided'}</strong>
        </div>
        <span className="binding-arrow" aria-hidden="true">→</span>
        <div>
          <span>Resolved Shopify order</span>
          <strong>{approval.order}</strong>
        </div>
      </div>

      <dl className="approval-detail-grid">
        <div>
          <dt>Requested action</dt>
          <dd>{ACTION_LABELS[approval.action]}</dd>
        </div>
        <div>
          <dt>Order amount</dt>
          <dd>{approval.amount}</dd>
        </div>
        <div>
          <dt>Gate rule</dt>
          <dd className="monospace-value">{approval.gate_rule}</dd>
        </div>
        <div>
          <dt>Safety flags</dt>
          <dd>
            {approval.flags.length > 0 ? (
              <span className="flag-list">
                {approval.flags.map((flag) => (
                  <span className="safety-flag" key={flag}>{flag}</span>
                ))}
              </span>
            ) : (
              'None'
            )}
          </dd>
        </div>
      </dl>

      <div className="gate-reason">
        <span>Why the gate passed</span>
        <p>{approval.gate_reason}</p>
      </div>

      {approval.current_shipping_address || approval.new_shipping_address ? (
        <div className="address-comparison">
          <AddressPanel
            heading="Current shipping address"
            address={approval.current_shipping_address}
          />
          <AddressPanel
            heading="Proposed shipping address"
            address={approval.new_shipping_address}
            emphasized
          />
        </div>
      ) : null}

      {errorMessage ? (
        <div className="decision-error" role="alert">
          <p>{errorMessage}</p>
          <button className="text-button" type="button" onClick={onRefresh}>
            Refresh ticket
          </button>
        </div>
      ) : null}

      <div className="decision-footer">
        <p>Approving runs this Shopify write immediately.</p>
        <div className="decision-actions">
          <button
            className="secondary-button reject-button"
            type="button"
            disabled={isSubmittingDecision}
            onClick={() => onDecide('reject')}
          >
            {activeDecision === 'reject' ? 'Rejecting…' : 'Reject action'}
          </button>
          <button
            className="primary-button approve-button"
            type="button"
            disabled={isSubmittingDecision}
            onClick={() => onDecide('approve')}
          >
            {activeDecision === 'approve' ? 'Executing…' : approveButtonLabel}
          </button>
        </div>
      </div>
    </section>
  )
}

interface AddressPanelProps {
  heading: string
  address: ShippingAddress | null
  emphasized?: boolean
}

function AddressPanel({ heading, address, emphasized = false }: AddressPanelProps) {
  const addressLines = address ? getAddressLines(address) : []
  return (
    <div className={`address-panel${emphasized ? ' proposed' : ''}`}>
      <span>{heading}</span>
      {addressLines.length > 0 ? (
        <address>
          {addressLines.map((addressLine) => (
            <span key={addressLine}>{addressLine}</span>
          ))}
        </address>
      ) : (
        <p>Not available</p>
      )}
    </div>
  )
}

function getAddressLines(address: ShippingAddress): string[] {
  const recipientName = [address.first_name, address.last_name].filter(Boolean).join(' ')
  const cityLine = [address.city, address.province, address.zip].filter(Boolean).join(', ')
  return [
    recipientName,
    address.company,
    address.address1,
    address.address2,
    cityLine,
    address.country,
    address.phone,
  ].filter((addressLine): addressLine is string => Boolean(addressLine))
}

function getApproveButtonLabel(approval: ApprovalPayload): string {
  if (approval.action === 'cancel_order') {
    return `Approve — cancel order ${approval.order}`
  }
  if (approval.action === 'issue_refund') {
    return `Approve — refund order ${approval.order}`
  }
  return `Approve — update address for ${approval.order}`
}
