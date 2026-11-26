import { createRouter, createWebHistory } from 'vue-router'

import Overview from '@/views/Overview.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'
import BudgetCycleView from '@/views/BudgetCycleView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    // 周期结算是专用页面，必须放在通配的模块路由之前
    { path: '/budget_cycle', name: 'budget-cycle', component: BudgetCycleView },
    { path: '/:moduleKey', name: 'module', component: WorkbenchView, props: true },
  ],
})

export default router
