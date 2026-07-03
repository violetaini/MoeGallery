<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Check, Coin, User } from '@element-plus/icons-vue'
import { galleryApi } from '../api/gallery'
import { clearInstallStatusCache } from '../router'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const checking = ref(false)
const status = ref(null)
const form = reactive({
  database_type: 'mysql',
  mysql_host: '127.0.0.1',
  mysql_port: 3306,
  mysql_database: 'anime_gallery',
  mysql_username: 'anime_gallery',
  mysql_password: '',
  admin_username: 'admin',
  admin_password: ''
})

const isInstalled = computed(() => Boolean(status.value?.installed))
const isPreviewMode = computed(() => route.query.preview === '1')

async function loadStatus() {
  checking.value = true
  try {
    status.value = await galleryApi.installStatus()
    if (status.value.installed && !isPreviewMode.value) {
      await router.replace('/login')
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '读取安装状态失败')
  } finally {
    checking.value = false
  }
}

function buildPayload() {
  const payload = {
    database_type: form.database_type,
    admin_username: form.admin_username.trim(),
    admin_password: form.admin_password
  }
  if (form.database_type === 'sqlite') {
    payload.sqlite_path = null
  } else {
    payload.mysql_host = form.mysql_host.trim()
    payload.mysql_port = Number(form.mysql_port)
    payload.mysql_database = form.mysql_database.trim()
    payload.mysql_username = form.mysql_username.trim()
    payload.mysql_password = form.mysql_password
  }
  return payload
}

async function submit() {
  if (isPreviewMode.value) {
    ElMessage.info('当前为预览模式，不会执行初始化')
    return
  }
  if (isInstalled.value) return
  if (!form.admin_username.trim() || !form.admin_password) {
    ElMessage.warning('请填写管理员账号和密码')
    return
  }
  loading.value = true
  try {
    const result = await galleryApi.install(buildPayload())
    if (result.restart_required) {
      ElMessage.success('初始化完成，请重启后端服务后登录')
    } else {
      ElMessage.success('初始化完成')
      clearInstallStatusCache()
      await router.replace('/login')
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '初始化失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadStatus()
})
</script>

<template>
  <main class="install-page" v-loading="checking">
    <section class="install-panel">
      <div class="install-panel__head">
        <span class="hero-eyebrow">Install</span>
        <h1>首次部署初始化</h1>
      </div>

      <el-form label-position="top" @submit.prevent>
        <section class="install-section">
          <div class="install-section__title">
            <el-icon><Coin /></el-icon>
            <strong>数据库</strong>
          </div>
          <el-radio-group v-model="form.database_type" class="install-database-tabs">
            <el-radio-button label="mysql">MySQL</el-radio-button>
            <el-radio-button label="sqlite">SQLite</el-radio-button>
          </el-radio-group>
          <div v-if="form.database_type === 'mysql'" class="install-form-grid">
            <el-form-item label="主机">
              <el-input v-model="form.mysql_host" />
            </el-form-item>
            <el-form-item label="端口">
              <el-input-number v-model="form.mysql_port" :min="1" :max="65535" controls-position="right" />
            </el-form-item>
            <el-form-item label="数据库名">
              <el-input v-model="form.mysql_database" />
            </el-form-item>
            <el-form-item label="用户名">
              <el-input v-model="form.mysql_username" />
            </el-form-item>
            <el-form-item class="install-form-grid__wide" label="数据库密码">
              <el-input v-model="form.mysql_password" type="password" show-password />
            </el-form-item>
          </div>
          <div v-else class="install-sqlite-note">
            <strong>SQLite</strong>
            <span>数据库文件将由系统自动保存到后端默认位置，无需手动选择路径。</span>
          </div>
          <div class="install-sqlite-note">
            <strong>存储位置</strong>
            <span>图片文件将由系统自动保存到项目根目录下的 storage 目录，无需手动选择路径。</span>
          </div>
        </section>

        <section class="install-section">
          <div class="install-section__title">
            <el-icon><User /></el-icon>
            <strong>管理员</strong>
          </div>
          <div class="install-form-grid">
            <el-form-item label="用户名">
              <el-input v-model="form.admin_username" autocomplete="username" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="form.admin_password" type="password" show-password autocomplete="new-password" />
            </el-form-item>
          </div>
        </section>

        <el-button
          type="primary"
          size="large"
          :icon="Check"
          :loading="loading"
          :disabled="isPreviewMode"
          class="install-submit"
          @click="submit"
        >
          {{ isPreviewMode ? '预览模式' : '开始初始化' }}
        </el-button>
      </el-form>
    </section>
  </main>
</template>
