import type { TicketDetailResponse, TicketSummary } from './types'

const TICKETS_API_PATH = '/api/tickets'

export async function listTickets(): Promise<TicketSummary[]> {
  return requestJson<TicketSummary[]>(TICKETS_API_PATH)
}

export async function getTicket(ticketId: string): Promise<TicketDetailResponse> {
  return requestJson<TicketDetailResponse>(
    `${TICKETS_API_PATH}/${encodeURIComponent(ticketId)}`,
  )
}

export async function createTicket(ticketText: string): Promise<TicketDetailResponse> {
  return requestJson<TicketDetailResponse>(TICKETS_API_PATH, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ ticket_text: ticketText }),
  })
}

async function requestJson<ResponseBody>(
  path: string,
  requestOptions?: RequestInit,
): Promise<ResponseBody> {
  const response = await fetch(path, requestOptions)
  if (!response.ok) {
    const errorBody = (await response.json().catch(() => null)) as {
      detail?: string
    } | null
    throw new Error(errorBody?.detail ?? `Request failed with status ${response.status}.`)
  }
  return response.json() as Promise<ResponseBody>
}
