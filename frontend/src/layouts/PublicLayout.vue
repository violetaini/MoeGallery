<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Setting } from '@element-plus/icons-vue'
import { useThemeStore } from '../stores/theme'

const router = useRouter()
const theme = useThemeStore()

onMounted(() => theme.apply())

function submitSearch(value) {
  const q = value?.trim()
  if (q) router.push({ path: '/search', query: { q } })
}
</script>

<template>
  <div class="app-shell public-shell">
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
        <RouterLink to="/gallery">图片库</RouterLink>
        <RouterLink to="/works">作品</RouterLink>
        <RouterLink to="/characters">角色</RouterLink>
        <RouterLink to="/tags">分级</RouterLink>
      </nav>
      <div class="nav-actions">
        <el-input
          class="nav-search"
          placeholder="搜索作品、角色"
          clearable
          :prefix-icon="Search"
          @keyup.enter="submitSearch($event.target.value)"
        />
        <el-button class="nav-entry-button" :icon="Setting" @click="$router.push('/admin')">后台入口</el-button>
      </div>
    </header>
    <main class="page-wrap">
      <RouterView v-slot="{ Component, route: viewRoute }">
        <Transition name="page-shell" mode="out-in">
          <div :key="viewRoute.fullPath" class="route-view" :class="{ 'route-view--home': viewRoute.name === 'home' }">
            <component :is="Component" />
          </div>
        </Transition>
      </RouterView>
    </main>
  </div>
</template>
