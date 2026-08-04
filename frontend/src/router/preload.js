export const loadAdminLayout = () => import('../layouts/AdminLayout.vue')
export const loadGallery = () => import('../views/Gallery.vue')
export const loadImageDetail = () => import('../views/ImageDetail.vue')
export const loadWorkList = () => import('../views/WorkList.vue')
export const loadWorkDetail = () => import('../views/WorkDetail.vue')
export const loadCharacterList = () => import('../views/CharacterList.vue')
export const loadCharacterDetail = () => import('../views/CharacterDetail.vue')
export const loadTagList = () => import('../views/TagList.vue')
export const loadSearch = () => import('../views/Search.vue')
export const loadLogin = () => import('../views/Login.vue')
export const loadInstall = () => import('../views/Install.vue')
export const loadDashboard = () => import('../views/admin/Dashboard.vue')
export const loadImageManage = () => import('../views/admin/ImageManage.vue')
export const loadImageUpload = () => import('../views/admin/ImageUpload.vue')
export const loadMetadataImport = () => import('../views/admin/MetadataImport.vue')
export const loadWorkManage = () => import('../views/admin/WorkManage.vue')
export const loadCharacterManage = () => import('../views/admin/CharacterManage.vue')
export const loadSettings = () => import('../views/admin/Settings.vue')
export const loadAdminWorkDetail = () => import('../views/admin/AdminWorkDetail.vue')
export const loadAdminCharacterDetail = () => import('../views/admin/AdminCharacterDetail.vue')
export const loadApiDocs = () => import('../views/admin/ApiDocs.vue')
export const loadUpdateCenter = () => import('../views/admin/UpdateCenter.vue')

const routeLoaders = {
  gallery: loadGallery,
  'image-detail': loadImageDetail,
  works: loadWorkList,
  'work-detail': loadWorkDetail,
  characters: loadCharacterList,
  'character-detail': loadCharacterDetail,
  tags: loadTagList,
  search: loadSearch,
  login: loadLogin,
  install: loadInstall,
  'admin-dashboard': loadDashboard,
  'admin-images': loadImageManage,
  'admin-image-upload': loadImageUpload,
  'admin-imports': loadMetadataImport,
  'admin-works': loadWorkManage,
  'admin-work-detail': loadAdminWorkDetail,
  'admin-characters': loadCharacterManage,
  'admin-character-detail': loadAdminCharacterDetail,
  'admin-api-docs': loadApiDocs,
  'admin-updates': loadUpdateCenter,
  'admin-settings': loadSettings
}

export function preloadRoute(routeName) {
  const loader = routeLoaders[routeName]
  return loader ? loader().catch(() => undefined) : Promise.resolve()
}

let publicRouteWarmupStarted = false

export function warmPublicRoutes() {
  if (publicRouteWarmupStarted || typeof window === 'undefined') return
  publicRouteWarmupStarted = true

  const routeNames = ['gallery', 'works', 'characters', 'tags', 'search']
  const schedule = typeof window.requestIdleCallback === 'function'
    ? (callback) => window.requestIdleCallback(callback, { timeout: 1200 })
    : (callback) => window.setTimeout(callback, 160)
  let index = 0

  const loadNext = () => {
    const routeName = routeNames[index]
    index += 1
    if (!routeName) return
    preloadRoute(routeName).finally(() => {
      if (index < routeNames.length) window.setTimeout(loadNext, 120)
    })
  }

  schedule(loadNext)
}
