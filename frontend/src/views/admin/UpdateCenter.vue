<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Refresh, VideoPlay } from '@element-plus/icons-vue'
import { galleryApi } from '../../api/gallery'

const checkLoading = ref(false)
const taskLoading = ref(false)
const starting = ref(false)
const updateInfo = ref(null)
const tasks = ref([])
const selectedTaskId = ref('')
const taskPage = ref(1)
const taskPageSize = 8
const taskTotal = ref(0)
const hasRunningTask = ref(false)
let pollingTimer = null
let pollingActive = false
let pollingGeneration = 0
let taskRequestSeq = 0
let taskLoadingSeq = 0
let updateCheckRequestSeq = 0

const runningStatuses = new Set(['queued', 'starting', 'downloading', 'verifying', 'prepared', 'backup', 'upgrading', 'restarting'])
const latestRelease = computed(() => updateInfo.value?.latest_release || {})
const latestVersion = computed(() => latestRelease.value.version || '未知')
const currentVersion = computed(() => updateInfo.value?.current_version || '未知')
const updateAvailable = computed(() => Boolean(updateInfo.value?.update_available))
const updateExecutionStatus = computed(() => updateInfo.value?.update_execution_status || {})
const updateExecutionModeText = computed(() => {
  if (!updateExecutionStatus.value.dry_run_available) return '不可用'
  if (!updateExecutionStatus.value.available) return '仅校验'
  return updateInfo.value?.update_execution_mode === 'launcher' ? '内置更新' : '本地任务'
})
const updateExecutionSeverityType = computed(() => {
  if (updateExecutionStatus.value.severity === 'ok') return 'success'
  if (updateExecutionStatus.value.severity === 'danger') return 'danger'
  return 'warning'
})
const updateExecutionHint = computed(() => {
  if (!updateInfo.value) return '等待检查更新环境'
  const details = [...(updateExecutionStatus.value.issues || []), ...(updateExecutionStatus.value.warnings || [])]
  return details[0] || updateExecutionStatus.value.message || '更新环境正常'
})
const canDryRun = computed(() => Boolean(latestRelease.value.available && updateExecutionStatus.value.dry_run_available && !hasRunningTask.value))
const canUpgrade = computed(() => Boolean(updateAvailable.value && updateExecutionStatus.value.available && !hasRunningTask.value))
const statusText = computed(() => {
  if (!updateInfo.value) return '未检查'
  if (!latestRelease.value.available) return '检查失败'
  return updateAvailable.value ? '发现新版本' : '已是最新'
})
const runningTask = computed(() => tasks.value.find((task) => runningStatuses.has(task.status)))
const selectedTask = computed(() => tasks.value.find((task) => task.id === selectedTaskId.value) || runningTask.value || tasks.value[0] || null)
const selectedTaskLog = computed(() => selectedTask.value?.log?.slice(-120) || [])

function statusLabel(status) {
  return {
    queued: '等待中',
    starting: '启动中',
    downloading: '下载中',
    verifying: '校验中',
    prepared: '等待安装',
    backup: '备份中',
    upgrading: '安装中',
    restarting: '重启中',
    success: '完成',
    failed: '失败'
  }[status] || status
}

function statusType(status) {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'danger'
  if (runningStatuses.has(status)) return 'warning'
  return 'info'
}

function formatTime(value) {
  if (!value) return '未开始'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

async function loadUpdateCheck() {
  const seq = ++updateCheckRequestSeq
  checkLoading.value = true
  try {
    const data = await galleryApi.checkUpdates()
    if (seq !== updateCheckRequestSeq) return
    updateInfo.value = data
  } catch (error) {
    if (seq === updateCheckRequestSeq) ElMessage.error(error?.response?.data?.detail || '检查更新失败')
  } finally {
    if (seq === updateCheckRequestSeq) checkLoading.value = false
  }
}

async function loadTasks({ silent = false } = {}) {
  const seq = ++taskRequestSeq
  const loadingSeq = silent ? null : ++taskLoadingSeq
  if (loadingSeq !== null) taskLoading.value = true
  try {
    const data = await galleryApi.updateTasks({ page: taskPage.value, page_size: taskPageSize })
    if (seq !== taskRequestSeq) return
    tasks.value = data.items || []
    taskTotal.value = Number(data.total || 0)
    hasRunningTask.value = Boolean(data.has_running_task)
    if (!tasks.value.length && taskTotal.value && taskPage.value > 1) {
      taskPage.value = Math.ceil(taskTotal.value / taskPageSize)
      await loadTasks({ silent })
      return
    }
    if (!selectedTaskId.value || !tasks.value.some((task) => task.id === selectedTaskId.value)) {
      selectedTaskId.value = tasks.value[0]?.id || ''
    }
  } catch (error) {
    if (!silent && seq === taskRequestSeq) ElMessage.error(error?.response?.data?.detail || '加载更新任务失败')
  } finally {
    if (loadingSeq !== null && loadingSeq === taskLoadingSeq) taskLoading.value = false
  }
}

function changeTaskPage(page) {
  if (page === taskPage.value) return
  taskPage.value = page
  void loadTasks()
}

async function refreshAll() {
  await Promise.all([loadUpdateCheck(), loadTasks()])
}

async function createTask(dryRun) {
  if (!latestRelease.value.available) {
    ElMessage.warning('请先完成更新检查')
    return
  }
  if (!dryRun && !updateAvailable.value) {
    ElMessage.info('当前已经是最新版本')
    return
  }
  if (dryRun && !updateExecutionStatus.value.dry_run_available) {
    ElMessage.warning(updateExecutionHint.value)
    return
  }
  if (!dryRun && !updateExecutionStatus.value.available) {
    ElMessage.warning(`正式更新未就绪：${updateExecutionHint.value}`)
    return
  }
  if (!dryRun) {
    const confirmed = await ElMessageBox.confirm(
      '更新会先备份并校验安装包，然后替换程序文件、执行数据库迁移并重启服务。执行期间后台可能短暂断开。',
      '确认开始更新',
      {
        confirmButtonText: '开始更新',
        cancelButtonText: '取消',
        type: 'warning'
      }
    ).then(() => true).catch(() => false)
    if (!confirmed) return
  }
  starting.value = true
  try {
    const task = await galleryApi.createUpdateTask({
      version: latestRelease.value.version,
      dry_run: dryRun,
      force: dryRun
    })
    ElMessage.success(dryRun ? '已开始下载校验' : '已开始更新')
    selectedTaskId.value = task.id
    taskPage.value = 1
    hasRunningTask.value = runningStatuses.has(task.status)
    await loadTasks({ silent: true })
    startPolling()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '创建更新任务失败')
    await loadTasks()
  } finally {
    starting.value = false
  }
}

function stopPolling() {
  pollingActive = false
  pollingGeneration += 1
  if (pollingTimer) window.clearTimeout(pollingTimer)
  pollingTimer = null
}

function startPolling() {
  if (pollingActive) return
  pollingActive = true
  const generation = pollingGeneration
  const poll = async () => {
    pollingTimer = null
    await loadTasks({ silent: true })
    if (!pollingActive || generation !== pollingGeneration) return
    if (!hasRunningTask.value) {
      pollingActive = false
      await loadUpdateCheck()
      return
    }
    pollingTimer = window.setTimeout(poll, 2000)
  }
  pollingTimer = window.setTimeout(poll, 2000)
}

onMounted(async () => {
  await refreshAll()
  if (hasRunningTask.value) startPolling()
})

onBeforeUnmount(() => {
  taskRequestSeq += 1
  updateCheckRequestSeq += 1
  stopPolling()
})
</script>

<template>
  <div class="update-center-page">
    <section class="update-summary-grid">
      <div class="update-summary-card">
        <span>当前版本</span>
        <strong>{{ currentVersion }}</strong>
        <small>{{ statusText }}</small>
      </div>
      <div class="update-summary-card">
        <span>最新版本</span>
        <strong>{{ latestVersion }}</strong>
        <small>{{ latestRelease.proxied ? '代理检查' : '直连检查' }}</small>
      </div>
      <div class="update-summary-card">
        <span>更新执行</span>
        <strong>{{ updateExecutionModeText }}</strong>
        <small>{{ updateExecutionStatus.message || '等待检查' }}</small>
      </div>
    </section>

    <el-alert
      v-if="updateInfo"
      class="update-env-alert"
      :type="updateExecutionSeverityType"
      :closable="false"
      show-icon
      :title="updateExecutionStatus.message || '更新环境检查完成'"
      :description="updateExecutionHint"
    />

    <section class="update-action-panel">
      <div class="update-action-copy">
        <strong>{{ updateAvailable ? `可更新至 ${latestVersion}` : '当前无需更新' }}</strong>
        <span>更新任务会下载 release 包并校验 SHA256；正式更新会自动备份、迁移数据库并重启服务。</span>
      </div>
      <div class="update-action-buttons">
        <el-button :icon="Refresh" :loading="checkLoading || taskLoading" @click="refreshAll">刷新</el-button>
        <el-button :icon="Download" :loading="starting" :disabled="!canDryRun" @click="createTask(true)">
          下载校验
        </el-button>
        <el-button
          type="primary"
          :icon="VideoPlay"
          :loading="starting"
          :disabled="!canUpgrade"
          @click="createTask(false)"
        >
          开始更新
        </el-button>
      </div>
    </section>

    <section class="update-task-layout">
      <div class="update-task-list" v-loading="taskLoading">
        <div class="update-task-list__head">
          <strong>更新任务</strong>
          <span>{{ taskTotal }} 条记录</span>
        </div>
        <button
          v-for="task in tasks"
          :key="task.id"
          type="button"
          class="update-task-row"
          :class="{ 'is-active': selectedTask?.id === task.id }"
          @click="selectedTaskId = task.id"
        >
          <div>
            <strong>{{ task.target_version || '未知版本' }}</strong>
            <span>{{ task.dry_run ? '下载校验' : '正式更新' }} · {{ formatTime(task.created_at) }}</span>
          </div>
          <el-tag :type="statusType(task.status)">{{ statusLabel(task.status) }}</el-tag>
        </button>
        <el-empty v-if="!taskLoading && !tasks.length" description="暂无更新任务" />
        <el-pagination
          v-if="taskTotal > taskPageSize"
          class="update-task-pagination"
          small
          background
          layout="prev, pager, next"
          :current-page="taskPage"
          :page-size="taskPageSize"
          :total="taskTotal"
          @current-change="changeTaskPage"
        />
      </div>

      <div class="update-task-detail">
        <template v-if="selectedTask">
          <div class="update-task-detail__head">
            <div>
              <strong>{{ selectedTask.target_version }}</strong>
              <span>{{ selectedTask.message }}</span>
            </div>
            <el-tag :type="statusType(selectedTask.status)">{{ statusLabel(selectedTask.status) }}</el-tag>
          </div>
          <el-progress :percentage="selectedTask.progress || 0" :status="selectedTask.status === 'failed' ? 'exception' : undefined" />
          <div class="update-task-meta">
            <span>任务 ID：{{ selectedTask.id }}</span>
            <span>开始：{{ formatTime(selectedTask.started_at) }}</span>
            <span>结束：{{ formatTime(selectedTask.finished_at) }}</span>
          </div>
          <pre class="update-task-log">{{ selectedTaskLog.join('\n') || '暂无日志' }}</pre>
        </template>
        <el-empty v-else description="选择或创建一个更新任务" />
      </div>
    </section>
  </div>
</template>
