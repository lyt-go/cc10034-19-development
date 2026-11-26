/** 周期结算专用接口：关账、退款归期、回执追查、旧预约领取配置。 */
import { request, fetchJson } from './client'
import type { ActionResult, EntryRow, PageResult } from '@/data/types'

export type BudgetPeriodRow = EntryRow
export type SettlementRow = EntryRow
export type RefundRow = EntryRow
export type ReservationRow = EntryRow

export type EligibilityResult = {
  reservation_id: number
  eligible: boolean
  reason: string
  额度来源?: string
  可用余额?: number
  结算单编号?: string
  结转剩余?: number
  gate?: string
  reservation?: ReservationRow
}

export type TraceResult = {
  receipt_no: string
  found: boolean
  refund?: RefundRow
  入账账期状态?: string
  说明?: string
}

async function postAction(path: string, body: Record<string, unknown>): Promise<ActionResult> {
  const response = await request(path, {
    method: 'POST',
    body: JSON.stringify(body),
  })
  if (!response.ok) throw new Error('接口请求失败')
  return await response.json()
}

export function listTable(table: string): Promise<PageResult> {
  return fetchJson<PageResult>(`/api/${table}?page=1&size=100`)
}

export function closePeriod(periodId: number): Promise<ActionResult> {
  return postAction(`/api/budget-cycle/periods/${periodId}/close`, {})
}

export function applyRefund(payload: {
  receipt_no: string
  charge_no: string
  amount: number
  arrival_period?: string
}): Promise<ActionResult> {
  return postAction('/api/budget-cycle/refunds', payload)
}

export function traceRefund(receiptNo: string): Promise<TraceResult> {
  return fetchJson<TraceResult>(`/api/budget-cycle/refunds/${encodeURIComponent(receiptNo)}/trace`)
}

export function checkEligibility(reservationId: number): Promise<EligibilityResult> {
  return fetchJson<EligibilityResult>(`/api/budget-cycle/reservations/${reservationId}/eligibility`)
}

export function claimReservation(reservationId: number): Promise<ActionResult> {
  return postAction(`/api/budget-cycle/reservations/${reservationId}/claim`, {})
}
