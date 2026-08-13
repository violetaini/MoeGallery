import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({
      resolvers: [ElementPlusResolver()],
      dts: false
    }),
    Components({
      resolvers: [ElementPlusResolver({ importStyle: 'css' })],
      dts: false
    })
  ],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('element-plus') || id.includes('@element-plus')) return undefined
          if (id.includes('vue-router')) return 'vue-router'
          if (id.includes('pinia')) return 'pinia'
          return 'vendor'
        }
      }
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/api-docs': 'http://127.0.0.1:8000',
      '/openapi.json': 'http://127.0.0.1:8000',
      '/media': 'http://127.0.0.1:8000',
      '/storage': 'http://127.0.0.1:8000'
    }
  }
})
