import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAdminStore = defineStore('admin', () => {
  const isCollapsed = ref(false)

  const toggleAdmin = () => {
    isCollapsed.value = !isCollapsed.value
  }
  return {
    isCollapsed,
    toggleAdmin
  }
}
)


