<template>
  <section class="page" data-module="budget_cycle">
    <header class="page-head">
      <div>
        <h2>周期结算</h2>
        <p class="page-desc">
          管理员提交待关闭账期，服务端按已执行费用与未清预约生成预算结算单；
          关账后跨窗口到达的退款跟随原账期归期，旧预约凭结算单结转额度领取噪声配置。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" data-testid="reload-all" type="button" @click="reloadAll">刷新数据</button>
      </div>
    </header>

    <div class="stat-row">
      <article class="stat-card">
        <span class="stat-label">开放/待关闭账期</span>
        <strong class="stat-value">{{ openPeriods.length }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">已关闭账期</span>
        <strong class="stat-value">{{ periods.filter((p) => p.status === '已关闭').length }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">预算结算单</span>
        <strong class="stat-value">{{ settlements.length }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">退款回执（含重复拦截）</span>
        <strong class="stat-value">{{ refunds.length }}</strong>
      </article>
    </div>

    <p v-if="message" class="page-foot" :class="messageKind" data-testid="cycle-message">{{ message }}</p>

    <!-- 区块一：账期关闭 -->
    <section class="cycle-section">
      <h3 class="cycle-title">① 账期关闭</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>账期编号</th>
            <th>周期名称</th>
            <th>关联预算</th>
            <th>额度</th>
            <th>已用（费用保留原周期）</th>
            <th>占用（未清预约）</th>
            <th>可用余额</th>
            <th>关账后退款累计</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in periods" :key="String(row.id)" :data-testid="`period-row-${row.id}`">
            <td>{{ row['账期编号'] }}</td>
            <td>{{ row['周期名称'] }}</td>
            <td>{{ row['关联预算'] }}</td>
            <td>{{ row['额度Epsilon'] }}</td>
            <td>{{ row['已用Epsilon'] }}</td>
            <td>{{ row['占用Epsilon'] }}</td>
            <td>{{ row['可用Epsilon'] }}</td>
            <td>{{ row['关账后退款累计'] }}</td>
            <td><span class="badge" :class="`badge-${row.status}`">{{ row.status }}</span></td>
            <td>
              <button
                v-if="row.status !== '已关闭'"
                class="link"
                type="button"
                :data-testid="`close-period-${row.id}`"
                @click="onClosePeriod(Number(row.id))"
              >
                提交关闭
              </button>
              <span v-else class="muted-text">结算单 {{ row['结算单编号'] }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 区块二：预算结算单 -->
    <section class="cycle-section">
      <h3 class="cycle-title">② 预算结算单（已执行费用 + 未清预约生成）</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>结算单编号</th>
            <th>账期</th>
            <th>额度</th>
            <th>已执行费用</th>
            <th>未清预约占用</th>
            <th>结算余额（不结转）</th>
            <th>结转预约</th>
            <th>已领取</th>
            <th>结转剩余</th>
            <th>关账后退款累计</th>
            <th>关账后净额</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in settlements" :key="String(row.id)" :data-testid="`settlement-row-${row.id}`">
            <td>{{ row['结算单编号'] }}</td>
            <td>{{ row['账期编号'] }}</td>
            <td>{{ row['额度Epsilon'] }}</td>
            <td>{{ row['已执行费用'] }}</td>
            <td>{{ row['未清预约占用'] }}</td>
            <td>{{ row['结算余额'] }}</td>
            <td>{{ row['结转预约Epsilon'] }}</td>
            <td>{{ row['已领取Epsilon'] }}</td>
            <td>{{ row['结转剩余'] }}</td>
            <td>{{ row['关账后退款累计'] }}</td>
            <td>{{ row['关账后净额'] }}</td>
            <td><span class="badge" :class="`badge-${row.status}`">{{ row.status }}</span></td>
          </tr>
          <tr v-if="!settlements.length">
            <td colspan="12" class="empty-state">暂无结算单，先在上方提交关闭一个账期</td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 区块三：待退款处理 + 回执追查 -->
    <section class="cycle-section">
      <h3 class="cycle-title">③ 待退款处理（回执幂等，关账后退款跟随原账期归期）</h3>
      <form class="refund-form" @submit.prevent="onApplyRefund">
        <label>
          <span>退款回执编号</span>
          <input v-model="refundForm.receipt_no" data-testid="refund-receipt-no" required placeholder="如 RCP-0001" />
        </label>
        <label>
          <span>费用编号</span>
          <input v-model="refundForm.charge_no" data-testid="refund-charge-no" required placeholder="如 CHG-0001" />
        </label>
        <label>
          <span>退款 Epsilon</span>
          <input v-model.number="refundForm.amount" data-testid="refund-amount" type="number" step="0.01" min="0.01" required />
        </label>
        <label>
          <span>退款到达窗口（账期）</span>
          <input v-model="refundForm.arrival_period" data-testid="refund-arrival-period" placeholder="如 P-202611，仅记录不改归期" />
        </label>
        <button class="btn primary" data-testid="submit-refund" type="submit" :disabled="submitting">
          {{ submitting ? '提交中…' : '提交退款回执' }}
        </button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th>回执编号</th>
            <th>费用编号</th>
            <th>退款Epsilon</th>
            <th>来源账期（费用原账期）</th>
            <th>入账账期</th>
            <th>到达窗口</th>
            <th>退款类型</th>
            <th>关联结算单</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in refunds" :key="String(row.id)" :data-testid="`refund-row-${row.id}`">
            <td>{{ row['回执编号'] }}</td>
            <td>{{ row['费用编号'] }}</td>
            <td>{{ row['退款Epsilon'] }}</td>
            <td>{{ row['来源账期'] }}</td>
            <td><strong>{{ row['入账账期'] }}</strong></td>
            <td>{{ row['到达窗口'] || '—' }}</td>
            <td>{{ row['退款类型'] }}</td>
            <td>{{ row['结算单编号'] || '—' }}</td>
            <td><span class="badge" :class="`badge-${row.status}`">{{ row.status }}</span></td>
          </tr>
          <tr v-if="!refunds.length">
            <td colspan="9" class="empty-state">暂无退款回执</td>
          </tr>
        </tbody>
      </table>

      <form class="trace-bar" @submit.prevent="onTrace">
        <label>
          <span>回执追查：额度进入了哪个账期？</span>
          <input v-model="traceNo" data-testid="trace-input" placeholder="输入回执编号" required />
        </label>
        <button class="btn" data-testid="trace-submit" type="button" @click="onTrace">追查</button>
      </form>
      <p v-if="traceResult" class="trace-result" data-testid="trace-result">
        <template v-if="traceResult.found">
          回执 {{ traceNo }} 的 {{ traceResult.refund?.['退款Epsilon'] }} Epsilon
          已入账 <strong>{{ traceResult.refund?.['入账账期'] }}</strong>
          （{{ traceResult['入账账期状态'] }}），来源账期 {{ traceResult.refund?.['来源账期'] }}；
          {{ traceResult['说明'] }}
        </template>
        <template v-else>未查到回执 {{ traceNo }}</template>
      </p>
    </section>

    <!-- 区块四：旧预约领取噪声配置 -->
    <section class="cycle-section">
      <h3 class="cycle-title">④ 旧预约领取噪声配置（噪声引擎按额度来源判定资格）</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>预约编号</th>
            <th>来源账期</th>
            <th>关联噪声配置</th>
            <th>预约Epsilon</th>
            <th>额度来源</th>
            <th>结算单</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in reservations" :key="String(row.id)" :data-testid="`reservation-row-${row.id}`">
            <td>{{ row['预约编号'] }}</td>
            <td>{{ row['账期编号'] }}</td>
            <td>{{ row['关联噪声配置'] }}</td>
            <td>{{ row['预约Epsilon'] }}</td>
            <td>{{ row['额度来源'] }}</td>
            <td>{{ row['结算单编号'] || '—' }}</td>
            <td><span class="badge" :class="`badge-${row.status}`">{{ row.status }}</span></td>
            <td class="row-actions">
              <button class="link" type="button" :data-testid="`check-${row.id}`" @click="onCheck(Number(row.id))">
                资格检查
              </button>
              <button
                v-if="row.status !== '已领取' && row.status !== '已失效'"
                class="link"
                type="button"
                :data-testid="`claim-${row.id}`"
                @click="onClaim(Number(row.id))"
              >
                领取配置
              </button>
            </td>
          </tr>
          <tr v-if="!reservations.length">
            <td colspan="8" class="empty-state">暂无未清预约</td>
          </tr>
        </tbody>
      </table>
      <ul v-if="eligibilityNotes.length" class="eligibility-list" data-testid="eligibility-notes">
        <li v-for="note in eligibilityNotes" :key="note.reservation_id">
          预约 {{ note.reservation_id }}：
          <span :class="note.eligible ? 'ok-text' : 'error-text'">
            {{ note.eligible ? '可领取' : '不可领取' }}
          </span>
          —— {{ note.reason }}
          <template v-if="note.额度来源">（额度来源：{{ note.额度来源 }}）</template>
        </li>
      </ul>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  applyRefund,
  checkEligibility,
  claimReservation,
  closePeriod,
  listTable,
  traceRefund,
  type EligibilityResult,
  type TraceResult,
} from '@/api/budget-cycle'
import type { EntryRow } from '@/data/types'

const periods = ref<EntryRow[]>([])
const settlements = ref<EntryRow[]>([])
const refunds = ref<EntryRow[]>([])
const reservations = ref<EntryRow[]>([])
const message = ref('')
const messageKind = ref('muted-text')
const submitting = ref(false)
const traceNo = ref('')
const traceResult = ref<TraceResult | null>(null)
const eligibilityNotes = ref<EligibilityResult[]>([])

const refundForm = ref({
  receipt_no: '',
  charge_no: '',
  amount: 0,
  arrival_period: '',
})

const openPeriods = computed(() => periods.value.filter((p) => p.status !== '已关闭'))

function flash(text: string, ok = true) {
  message.value = text
  messageKind.value = ok ? 'ok-text' : 'error-text'
}

async function reloadAll() {
  try {
    const [periodPage, settlementPage, refundPage, reservationPage] = await Promise.all([
      listTable('budget_period'),
      listTable('budget_settlement'),
      listTable('budget_refund'),
      listTable('budget_reservation'),
    ])
    periods.value = periodPage.items
    settlements.value = settlementPage.items
    refunds.value = refundPage.items
    reservations.value = reservationPage.items
  } catch (error) {
    flash(error instanceof Error ? error.message : '周期结算数据读取失败', false)
  }
}

async function onClosePeriod(periodId: number) {
  try {
    const result = await closePeriod(periodId)
    flash(result.message, result.ok)
    await reloadAll()
  } catch (error) {
    flash(error instanceof Error ? error.message : '关账失败', false)
  }
}

async function onApplyRefund() {
  submitting.value = true
  try {
    const result = await applyRefund({ ...refundForm.value })
    flash(result.message, result.ok)
    if (result.ok) {
      refundForm.value = { receipt_no: '', charge_no: '', amount: 0, arrival_period: '' }
    }
    await reloadAll()
  } catch (error) {
    flash(error instanceof Error ? error.message : '退款提交失败', false)
  } finally {
    submitting.value = false
  }
}

async function onTrace() {
  if (!traceNo.value.trim()) return
  try {
    traceResult.value = await traceRefund(traceNo.value.trim())
  } catch (error) {
    flash(error instanceof Error ? error.message : '回执追查失败', false)
  }
}

async function onCheck(reservationId: number) {
  try {
    const result = await checkEligibility(reservationId)
    eligibilityNotes.value = [
      result,
      ...eligibilityNotes.value.filter((n) => n.reservation_id !== reservationId),
    ]
    flash(result.reason, result.eligible)
  } catch (error) {
    flash(error instanceof Error ? error.message : '资格检查失败', false)
  }
}

async function onClaim(reservationId: number) {
  try {
    const result = await claimReservation(reservationId)
    flash(result.message, result.ok)
    await reloadAll()
  } catch (error) {
    flash(error instanceof Error ? error.message : '领取配置失败', false)
  }
}

onMounted(reloadAll)
</script>
