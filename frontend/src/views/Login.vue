<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock, User } from '@element-plus/icons-vue'
import { setAuthSession } from '../api/client'
import { galleryApi } from '../api/gallery'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const form = reactive({
  username: '',
  password: ''
})

async function submit() {
  if (!form.username.trim() || !form.password) {
    ElMessage.warning('请输入账号和密码')
    return
  }
  loading.value = true
  try {
    const session = await galleryApi.login({
      username: form.username.trim(),
      password: form.password
    })
    setAuthSession(session)
    await router.replace(route.query.redirect || '/admin')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-panel">
      <div class="login-panel__shine"></div>
      <div class="login-panel__poster">
        <img src="/avatar.webp" alt="Anime Gallery" />
      </div>
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="账号">
          <el-input v-model="form.username" :prefix-icon="User" autocomplete="username" @keyup.enter="submit" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            :prefix-icon="Lock"
            type="password"
            show-password
            autocomplete="current-password"
            @keyup.enter="submit"
          />
        </el-form-item>
        <div class="login-actions">
          <el-button type="primary" size="large" :loading="loading" @click="submit">登录</el-button>
          <el-button size="large" plain @click="router.push('/')">返回前台</el-button>
        </div>
      </el-form>
    </section>
  </main>
</template>
