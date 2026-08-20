<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Search, Setting } from '@element-plus/icons-vue'
import { applyLightTheme } from '../stores/theme'
import { preloadRoute } from '../router/preload'

const route = useRoute()
const router = useRouter()

const isHomeLayoutActive = computed(() => route.name === 'home')

onMounted(applyLightTheme)

function submitSearch(value) {
  const q = value?.trim()
  if (q) router.push({ path: '/search', query: { q } })
}

function preload(routeName) {
  void preloadRoute(routeName)
}
</script>

<template>
  <div class="app-shell public-shell" :class="{ 'public-shell--home': isHomeLayoutActive }">
    <header class="top-nav">
      <RouterLink class="brand" to="/">
        <img class="brand-avatar" src="/avatar.webp" alt="Anime Gallery" />
        <span class="brand-copy">
          <strong>Anime Gallery</strong>
          <small>Image archive</small>
        </span>
      </RouterLink>
      <nav class="nav-links">
        <RouterLink to="/">首页</RouterLink>
        <RouterLink to="/gallery" @pointerenter="preload('gallery')" @focus="preload('gallery')">图片库</RouterLink>
        <RouterLink to="/works" @pointerenter="preload('works')" @focus="preload('works')">作品</RouterLink>
        <RouterLink to="/characters" @pointerenter="preload('characters')" @focus="preload('characters')">角色</RouterLink>
        <RouterLink to="/tags" @pointerenter="preload('tags')" @focus="preload('tags')">分级</RouterLink>
      </nav>
      <div class="nav-actions">
        <el-input
          class="nav-search"
          placeholder="搜索作品、角色"
          clearable
          :prefix-icon="Search"
          @focus="preload('search')"
          @keyup.enter="submitSearch($event.target.value)"
        />
        <el-button class="nav-entry-button" :icon="Setting" @pointerenter="preload('admin-dashboard')" @click="$router.push('/admin')">后台入口</el-button>
      </div>
    </header>
    <main class="page-wrap" :class="{ 'page-wrap--home': isHomeLayoutActive }">
      <RouterView v-slot="{ Component, route: viewRoute }">
        <div :key="viewRoute.fullPath" class="route-view" :class="{ 'route-view--home': viewRoute.name === 'home' }">
          <component :is="Component" />
        </div>
      </RouterView>
    </main>
  </div>
</template>
