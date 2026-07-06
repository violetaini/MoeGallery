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
let pollingTimer = null

const runningStatuses = new Set(['queued', 'starting', 'downloading', 'verifying', 'backup', 'upgrading', 'restarting'])
const latestRelease = computed(() => updateInfo.value?.latest_release || {})
const latestVersion = computed(() => latestRelease.value.version || '未知')
const currentVersion = computed(() => updateInfo.value?.current_version || '未知')
const updateAvailable = computed(() => Boolean(updateInfo.value?.update_available))
const updaterStatus = computed(() => updateInfo.value?.updater_status || {})
const updaterModeText = computed(() => {
  if (!updaterStatus.value.dry_run_available) return '不可用'
  if (!updaterStatus.value.available) return '仅校验'
  return updateInfo.value?.updater_mode === 'command' ? '独立服务' : '本地任务'
})
const updaterSeverityType = computed(() => {
  if (updaterStatus.value.severity === 'ok') return 'success'
  if (updaterStatus.value.severity === 'danger') return 'danger'
  return 'warning'
})
const updaterHint = computed(() => {
  if (!updateInfo.value) return '等待检查更新环境'
  const details = [...(updaterStatus.value.issues || []), ...(updaterStatus.value.warnings || [])]
  return details[0] || updaterStatus.value.message || '更新环境正常'
})
const canDryRun = computed(() => Boolean(latestRelease.value.available && updaterStatus.value.dry_run_available && !runningTask.value))
const canUpgrade = computed(() => Boolean(updateAvailable.value && updaterStatus.value.available && !runningTask.value))
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
  checkLoading.value = true
  try {
    updateInfo.value = await galleryApi.checkUpdates()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '检查更新失败')
  } finally {
    checkLoading.value = false
  }
}

async function loadTasks() {
  taskLoading.value = true
  try {
    const data = await galleryApi.updateTasks({ limit: 20 })
    tasks.value = data.items || []
    if (!selectedTaskId.value || !tasks.value.some((task) => task.id === selectedTaskId.value)) {
      selectedTaskId.value = tasks.value[0]?.id || ''
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '加载更新任务失败')
  } finally {
    taskLoading.value = false
  }
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
  if (dryRun && !updaterStatus.value.dry_run_available) {
    ElMessage.warning(updaterHint.value)
    return
  }
  if (!dryRun && !updaterStatus.value.available) {
    ElMessage.warning(`正式更新未就绪：${updaterHint.value}`)
    return
  }
  if (!dryRun) {
    await ElMessageBox.confirm(
      '更新会先备份并校验安装包，然后替换程序文件、执行数据库迁移并重启服务。执行期间后台可能短暂断开。',
      '确认开始更新',
      {
        confirmButtonText: '开始更新',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
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
    tasks.value = [task, ...tasks.value.filter((item) => item.id !== task.id)]
    startPolling()
  } catch (error) {
    if (error === 'cancel') return
    ElMessage.error(error?.response?.data?.detail || '创建更新任务失败')
    await loadTasks()
  } finally {
    starting.value = false
  }
}

function startPolling() {
  if (pollingTimer) return
  pollingTimer = window.setInterval(async () => {
    await loadTasks()
    if (!runningTask.value) {
      window.clearInterval(pollingTimer)
      pollingTimer = null
      await loadUpdateCheck()
    }
  }, 2000)
}

onMounted(async () => {
  await refreshAll()
  if (runningTask.value) startPolling()
})

onBeforeUnmount(() => {
  if (pollingTimer) window.clearInterval(pollingTimer)
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
        <strong>{{ updaterModeText }}</strong>
        <small>{{ updaterStatus.message || '等待检查' }}</small>
      </div>
    </section>

    <el-alert
      v-if="updateInfo"
      class="update-env-alert"
      :type="updaterSeverityType"
      :closable="false"
      show-icon
      :title="updaterStatus.message || '更新环境检查完成'"
      :description="updaterHint"
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
          <span>{{ tasks.length }} 条记录</span>
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
