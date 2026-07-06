<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  DataBoard,
  Document,
  Close,
  FolderOpened,
  FolderAdd,
  Menu as MenuIcon,
  Picture,
  Refresh,
  Setting,
  SwitchButton,
  Upload,
  User
} from '@element-plus/icons-vue'
import { adminAvatarUrlFromImage, clearAuthSession, getAuthAvatar, getAuthUser, setAuthSession } from '../api/client'
import { galleryApi } from '../api/gallery'

const router = useRouter()
const route = useRoute()
const username = ref(getAuthUser() || 'admin')
const avatarUrl = ref(getAuthAvatar() || '/avatar.webp')
const mobileMenuOpen = ref(false)
const pageTitle = computed(() => route.meta?.title || '后台首页')

const activeMenu = computed(() => {
  if (route.path === '/admin') return '/admin'
  if (route.path.startsWith('/admin/images/upload')) return '/admin/images/upload'
  if (route.path.startsWith('/admin/images')) return '/admin/images'
  if (route.path.startsWith('/admin/imports')) return '/admin/imports'
  if (route.path.startsWith('/admin/works')) return '/admin/works'
  if (route.path.startsWith('/admin/characters')) return '/admin/characters'
  if (route.path.startsWith('/admin/api-docs')) return '/admin/api-docs'
  if (route.path.startsWith('/admin/updates')) return '/admin/updates'
  if (route.path.startsWith('/admin/settings')) return '/admin/settings'
  return '/admin'
})

async function refreshAdminProfile() {
  try {
    const profile = await galleryApi.me()
    username.value = profile.username || 'admin'
    avatarUrl.value = adminAvatarUrlFromImage(profile.avatar_image) || '/avatar.webp'
    setAuthSession({ username: profile.username, avatar_image: profile.avatar_image })
  } catch {
    username.value = getAuthUser() || 'admin'
    avatarUrl.value = getAuthAvatar() || '/avatar.webp'
  }
}

async function logout() {
  try {
    await galleryApi.logout()
  } finally {
    clearAuthSession()
    router.replace('/login')
  }
}

watch(
  () => route.fullPath,
  () => {
    mobileMenuOpen.value = false
  }
)

onMounted(refreshAdminProfile)
</script>

<template>
  <el-container class="admin-shell" :class="{ 'is-menu-open': mobileMenuOpen }">
    <button
      class="admin-menu-backdrop"
      type="button"
      aria-label="关闭管理菜单"
      @click="mobileMenuOpen = false"
    ></button>
    <el-aside width="232px" class="admin-aside">
      <RouterLink class="admin-brand" to="/">
        <img class="brand-avatar" :src="avatarUrl" alt="Anime Gallery" />
        <span class="brand-copy">
          <strong>Anime Gallery</strong>
          <small>Admin control</small>
        </span>
      </RouterLink>
      <div class="admin-mobile-drawer-head">
        <span>管理菜单</span>
        <el-button :icon="Close" circle text aria-label="关闭管理菜单" @click="mobileMenuOpen = false" />
      </div>
      <el-menu router :default-active="activeMenu" class="admin-menu">
        <el-menu-item index="/admin">
          <el-icon><DataBoard /></el-icon>
          <span>后台首页</span>
        </el-menu-item>
        <el-menu-item index="/admin/images">
          <el-icon><Picture /></el-icon>
          <span>图片管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/images/upload">
          <el-icon><Upload /></el-icon>
          <span>图片上传</span>
        </el-menu-item>
        <el-menu-item index="/admin/imports">
          <el-icon><FolderAdd /></el-icon>
          <span>批量导入</span>
        </el-menu-item>
        <el-menu-item index="/admin/works">
          <el-icon><FolderOpened /></el-icon>
          <span>作品管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/characters">
          <el-icon><User /></el-icon>
          <span>角色管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/updates">
          <el-icon><Refresh /></el-icon>
          <span>更新中心</span>
        </el-menu-item>
        <el-menu-item index="/admin/settings">
          <el-icon><Setting /></el-icon>
          <span>系统设置</span>
        </el-menu-item>
        <el-menu-item index="/admin/api-docs">
          <el-icon><Document /></el-icon>
          <span>API 文档</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="admin-header">
        <div class="admin-title">
          <el-button
            class="admin-mobile-menu-button"
            :icon="MenuIcon"
            circle
            aria-label="打开管理菜单"
            @click="mobileMenuOpen = true"
          />
          <span>{{ pageTitle }}</span>
        </div>
        <div class="admin-header-actions">
          <span class="admin-status-pill">在线管理</span>
          <img class="admin-user-avatar" :src="avatarUrl" alt="" />
          <span class="muted">{{ username }}</span>
          <el-button @click="$router.push('/')">返回前台</el-button>
          <el-button :icon="SwitchButton" @click="logout">退出</el-button>
        </div>
      </el-header>
      <el-main class="admin-main">
        <RouterView v-slot="{ Component, route }">
          <div :key="route.path" class="route-view">
            <component :is="Component" />
          </div>
        </RouterView>
      </el-main>
    </el-container>
  </el-container>
</template>
