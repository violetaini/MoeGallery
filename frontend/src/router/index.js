import { createRouter, createWebHistory } from 'vue-router'

import PublicLayout from '../layouts/PublicLayout.vue'
import AdminLayout from '../layouts/AdminLayout.vue'
import Home from '../views/Home.vue'
import Gallery from '../views/Gallery.vue'
import ImageDetail from '../views/ImageDetail.vue'
import WorkList from '../views/WorkList.vue'
import WorkDetail from '../views/WorkDetail.vue'
import CharacterList from '../views/CharacterList.vue'
import CharacterDetail from '../views/CharacterDetail.vue'
import TagList from '../views/TagList.vue'
import Search from '../views/Search.vue'
import Login from '../views/Login.vue'
import Install from '../views/Install.vue'
import Dashboard from '../views/admin/Dashboard.vue'
import ImageManage from '../views/admin/ImageManage.vue'
import ImageUpload from '../views/admin/ImageUpload.vue'
import MetadataImport from '../views/admin/MetadataImport.vue'
import WorkManage from '../views/admin/WorkManage.vue'
import CharacterManage from '../views/admin/CharacterManage.vue'
import Settings from '../views/admin/Settings.vue'
import AdminWorkDetail from '../views/admin/AdminWorkDetail.vue'
import AdminCharacterDetail from '../views/admin/AdminCharacterDetail.vue'
import ApiDocs from '../views/admin/ApiDocs.vue'
import { clearAuthSession, setAuthSession } from '../api/client'
import { galleryApi } from '../api/gallery'

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
        return true
      })
      .catch(() => {
        clearAuthSession()
        return false
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
        { path: 'gallery', name: 'gallery', component: Gallery },
        { path: 'images/:id', name: 'image-detail', component: ImageDetail },
        { path: 'works', name: 'works', component: WorkList },
        { path: 'works/:id', name: 'work-detail', component: WorkDetail },
        { path: 'characters', name: 'characters', component: CharacterList },
        { path: 'characters/:id', name: 'character-detail', component: CharacterDetail },
        { path: 'tags', name: 'tags', component: TagList },
        { path: 'search', name: 'search', component: Search }
      ]
    },
    {
      path: '/login',
      name: 'login',
      component: Login
    },
    {
      path: '/install',
      name: 'install',
      component: Install
    },
    {
      path: '/admin/api-docs',
      name: 'admin-api-docs',
      component: ApiDocs,
      meta: { requiresAuth: true }
    },
    {
      path: '/admin',
      component: AdminLayout,
      meta: { requiresAuth: true },
      children: [
        { path: '', name: 'admin-dashboard', component: Dashboard, meta: { title: '后台首页' } },
        { path: 'images', name: 'admin-images', component: ImageManage, meta: { title: '图片管理' } },
        { path: 'images/upload', name: 'admin-image-upload', component: ImageUpload, meta: { title: '图片上传' } },
        { path: 'imports', name: 'admin-imports', component: MetadataImport, meta: { title: '批量导入' } },
        { path: 'works', name: 'admin-works', component: WorkManage, meta: { title: '作品管理' } },
        { path: 'works/:id', name: 'admin-work-detail', component: AdminWorkDetail, meta: { title: '作品主页' } },
        { path: 'characters', name: 'admin-characters', component: CharacterManage, meta: { title: '角色管理' } },
        { path: 'characters/:id', name: 'admin-character-detail', component: AdminCharacterDetail, meta: { title: '角色主页' } },
        { path: 'settings', name: 'admin-settings', component: Settings, meta: { title: '系统设置' } }
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
    const authenticated = await ensureAuthSession()
    if (!authenticated) {
      return { path: '/login', query: { redirect: to.fullPath } }
    }
  }
  if (to.name === 'login') {
    const authenticated = await ensureAuthSession()
    if (authenticated) return { path: '/admin' }
  }
  return true
})

export default router
