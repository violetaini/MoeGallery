import { createRouter, createWebHistory } from 'vue-router'

import PublicLayout from '../layouts/PublicLayout.vue'
import Home from '../views/Home.vue'
import { clearAuthSession, setAuthSession } from '../api/client'
import { galleryApi } from '../api/gallery'
import {
  loadAdminCharacterDetail,
  loadAdminLayout,
  loadAdminWorkDetail,
  loadApiDocs,
  loadCharacterDetail,
  loadCharacterList,
  loadCharacterManage,
  loadDashboard,
  loadGallery,
  loadImageDetail,
  loadImageManage,
  loadImageUpload,
  loadInstall,
  loadLogin,
  loadMetadataImport,
  loadSearch,
  loadSettings,
  loadTagList,
  loadUpdateCenter,
  loadWorkDetail,
  loadWorkList,
  loadWorkManage
} from './preload'

export { warmPublicRoutes } from './preload'

let installStatusCache = null
let authProbePromise = null

export function clearInstallStatusCache() {
  installStatusCache = null
}

async function getInstallStatus() {
  if (!installStatusCache) {
    installStatusCache = galleryApi.installStatus().catch(() => ({ installed: true }))
  }
  return installStatusCache
}

async function ensureAuthSession() {
  if (!authProbePromise) {
    authProbePromise = galleryApi.me()
      .then((profile) => {
        setAuthSession({ username: profile.username, avatar_image: profile.avatar_image })
        return profile
      })
      .catch(() => {
        clearAuthSession()
        return null
      })
      .finally(() => {
        authProbePromise = null
      })
  }
  return authProbePromise
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: PublicLayout,
      children: [
        { path: '', name: 'home', component: Home },
        { path: 'gallery', name: 'gallery', component: loadGallery },
        { path: 'images/:id', name: 'image-detail', component: loadImageDetail },
        { path: 'works', name: 'works', component: loadWorkList },
        { path: 'works/:id', name: 'work-detail', component: loadWorkDetail },
        { path: 'characters', name: 'characters', component: loadCharacterList },
        { path: 'characters/:id', name: 'character-detail', component: loadCharacterDetail },
        { path: 'tags', name: 'tags', component: loadTagList },
        { path: 'search', name: 'search', component: loadSearch }
      ]
    },
    {
      path: '/login',
      name: 'login',
      component: loadLogin
    },
    {
      path: '/install',
      name: 'install',
      component: loadInstall
    },
    {
      path: '/admin/api-docs',
      name: 'admin-api-docs',
      component: loadApiDocs,
      meta: { requiresAuth: true }
    },
    {
      path: '/admin',
      component: loadAdminLayout,
      meta: { requiresAuth: true },
      children: [
        { path: '', name: 'admin-dashboard', component: loadDashboard, meta: { title: '后台首页' } },
        { path: 'images', name: 'admin-images', component: loadImageManage, meta: { title: '图片管理' } },
        { path: 'images/upload', name: 'admin-image-upload', component: loadImageUpload, meta: { title: '图片上传' } },
        { path: 'imports', name: 'admin-imports', component: loadMetadataImport, meta: { title: '批量导入' } },
        { path: 'works', name: 'admin-works', component: loadWorkManage, meta: { title: '作品管理' } },
        { path: 'works/:id', name: 'admin-work-detail', component: loadAdminWorkDetail, meta: { title: '作品主页' } },
        { path: 'characters', name: 'admin-characters', component: loadCharacterManage, meta: { title: '角色管理' } },
        { path: 'characters/:id', name: 'admin-character-detail', component: loadAdminCharacterDetail, meta: { title: '角色主页' } },
        { path: 'updates', name: 'admin-updates', component: loadUpdateCenter, meta: { title: '更新中心' } },
        { path: 'settings', name: 'admin-settings', component: loadSettings, meta: { title: '系统设置' } }
      ]
    }
  ],
  scrollBehavior() {
    return { top: 0 }
  }
})

router.beforeEach(async (to) => {
  const installStatus = await getInstallStatus()
  const isInstallPreview = to.name === 'install' && to.query.preview === '1'
  if (!installStatus.installed && to.name !== 'install') {
    return { path: '/install' }
  }
  if (installStatus.installed && to.name === 'install' && !isInstallPreview) {
    return { path: '/login' }
  }
  if (to.meta.requiresAuth) {
    const profile = await ensureAuthSession()
    if (!profile) {
      return { path: '/login', query: { redirect: to.fullPath } }
    }
    if (profile.password_change_required && to.name !== 'admin-settings') {
      return { path: '/admin/settings', query: { password_change: '1' } }
    }
  }
  if (to.name === 'login') {
    const profile = await ensureAuthSession()
    if (profile?.password_change_required) {
      return { path: '/admin/settings', query: { password_change: '1' } }
    }
    if (profile) return { path: '/admin' }
  }
  return true
})

export default router
