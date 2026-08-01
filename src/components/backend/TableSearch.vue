<script setup lang="ts">
import { ref, computed } from "vue";
import type { FormInstance } from "element-plus";
import type { FormItemConfig } from "@/types";

const props = defineProps<{
  //？：可选属性，没有就是什么都不渲染
  formItem?: FormItemConfig[];
}>();
const emit = defineEmits(["search"]);
const formRef = ref<FormInstance>();

//用计算属性处理formItem，给每个item添加col属性
//不要直接修改props.formItem，因为props是只读的，不能直接修改
const formItemAttr = computed(() =>
  (props.formItem || []).map((item) => ({
    ...item,
    col: { xs: 24, sm: 12, md: 8, lg: 6, xl: 4 },
  })),
);

const isComp = (comp: string) => {
  // 简写 → Element Plus 组件名的映射
  return {
    input: "el-input",
    select: "el-select",
  }[comp];
};

// 表单数据
// Record<string, string>：键值对，键是字符串，值是字符串
const formData = ref<Record<string, string>>({});

// 搜索方法
const handleSearch = (formData: Record<string, string>) => {
  console.log(formData);
  emit("search", formData);
};

// 重置方法
const handleReset = (formEl: FormInstance | undefined) => {
  //先重置表单，然后再触发查询
  if (!formEl) return;
  formEl.resetFields();
  emit("search", formData);
};
</script>

<template>
  <!-- 表格搜索组件 -->
  <el-form :model="formData" ref="formRef">
    <el-row :gutter="24">
      <template v-for="item in formItemAttr" :key="item.prop">
        <el-col v-bind="item.col">
          <!-- 遍历 formItem，根据配置动态渲染表单项 -->
          <el-form-item :label="item.label" :prop="item.prop">
            <component
              :is="isComp(item.comp)"
              v-model="formData[item.prop]"
              :placeholder="item.placeholder"
            >
              <template v-if="item.comp === 'select'">
                <el-option
                  v-for="option in item.options"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </template>
            </component>
          </el-form-item>
        </el-col>
      </template>
    </el-row>
    <el-row>
      <el-button type="primary" @click="handleSearch(formData)">查询</el-button>
      <el-button @click="handleReset(formRef)">重置</el-button>
    </el-row>
  </el-form>
</template>

<style scoped></style>
