<script setup lang="ts">
import { ref , computed ,nextTick ,watch } from "vue";
import { ElMessage } from "element-plus";
import { uploadFile } from "@/apis/admin";
import { fileBaseURL } from "@/config/index";
import RichTextEditor from "@/components/backend/RichTextEditor.vue";
import { createArticle, updateArticle } from "@/apis/admin";

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  article: {
    type: Object,
    //为了加字段判断是新增还是编辑
    default: null
  },
  categoryList: {
    type: Array as () => { label: string; value: string }[],
    default: () => []
  }
})

//通过defineEmits定义事件，然后传值给父组件
const emit = defineEmits(['update:modelValue','success'])
const dialogVisible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})
//判断是否是编辑文章
//如果id存在，就是编辑文章，否则就是新增文章，
const isEdit = computed(() => !!props.article?.id)

//要对数据进行监听，回显文章详情
watch(() => props.article, (newVal) => {
  if (newVal) {
    formData.value = { ...newVal }
    //使用现有的id
    businessId.value = newVal.id
    //加？判断，防止coverImage为空时，拼接空字符串
    imgUrl.value = newVal.coverImage ? `${fileBaseURL}${newVal.coverImage}` : ''
  }
})

//新增文章弹窗表单数据
const formData = ref<Record<string, any>>({
    "title": "",
    "content": "",
    "coverImage": "",
    "categoryId": "",
    "summary": "",
    "tags": "",
    "id": "",
    "tagArray": []
})

//表单校验规则
const rules = ref<any>({
  title: [
    { required: true, message: '请输入文章标题', trigger: 'blur' },
    { max: 200, message: '文章标题最多200个字符', trigger: 'blur' }
  ],
  categoryId: [
    { required: true, message: '请选择分类', trigger: 'change' }
  ],
  summary: [
    { max: 1000, message: '文章摘要最多1000个字符', trigger: 'blur' }
  ],
  tags: [
    { max: 100, message: '文章标签最多100个字符', trigger: 'blur' }
  ],
  content: [
    { required: true, message: '请输入文章内容', trigger: 'blur' },
    { max: 5000, message: '文章内容最多5000个字符', trigger: 'blur' }
  ],
})

const commonTags = [
  '情绪管理', '焦虑', '抑郁', '压力', '睡眠', 
  '冥想', '正念', '放松', '心理健康', '自我成长',
  '人际关系', '工作压力', '学习方法', '生活技巧'
]

//上传封面的业务ID（新增时随机生成，编辑时使用文章ID）
const businessId = ref<string>('')

//上传封面
const imgUrl =ref('')
const beforeUpload = (file: File) => {
  //文件校验
  //startsWith() 方法用于判断字符串是否以指定的字符或字符串开头
  const isImg= file.type.startsWith('image/')
  const isSize = file.size <= 5242880 // 5MB
  if (!isImg) {
    ElMessage.error('上传图片只能是 JPG/PNG 格式!')
    //返回false，阻止上传
    return false
  }
  if (!isSize) {
    ElMessage.error('上传图片大小不能超过5MB!')
    //返回false，阻止上传
    return false
  }
  //返回true，允许上传
  return true
}
const handleUploadRequest = async (options: any) => {
  const file = options.file
  // 新增时生成UUID，编辑时已有businessId
  businessId.value = businessId.value || crypto.randomUUID()
  const fileRes = await uploadFile(file, { id: businessId.value })
  //拼接文件路径
  imgUrl.value = `${fileBaseURL}${fileRes.filePath}`
  //传给后端的地址，接收相对路径
  formData.value.coverImage = fileRes.filePath
  console.log(fileRes)
}
//删除封面
const removeCover = () => {
  imgUrl.value = ''
  formData.value.coverImage = ''
}

//富文本 — v-model 已自动同步 content，这里只做额外处理
const handleContentChange = (payload: { html: string; text: string }) => {
  // v-model 已自动同步，这里可用于字数统计等
  console.log(payload)
}

const editorRef = ref<any>(null)
const handleEditorCreate = (editor: any) => {
  editorRef.value = editor
  // 编辑模式：把已有内容回填到编辑器
  if (formData.value.content) {
    // nextTick等待编辑器实例创建完成 ，再回填内容
    nextTick(() => {
      editorRef.value.setHtml(formData.value.content)
    })
  }
}

//表单校验
const formRef = ref<any>(null)

const btnPreview = ref(false)

const handleClose = () => {
  // 关闭弹窗
  emit('update:modelValue', false)
  // 重置表单
  // formRef.value.resetFields()
  formData.value = {
    title: '',
    content: '',
    coverImage: '',
    categoryId: '',
    summary: '',
    tags: '',
    id: '',
    tagArray: []
  }
  imgUrl.value = ''
  businessId.value = ''
}
const loading = ref(false)

// 提交（新增/编辑）
const handleSubmit = () => {
  formRef.value.validate((valid: boolean, fields: any) => {
    if (valid) {
      loading.value = true

      const { tagArray, ...rest } = formData.value
      const submitData: Record<string, any> = {
        ...rest,
        tags: tagArray.join(',')
      }
      //新增时，id为空，编辑时，id存在，要传id给后端
      if (!isEdit.value) {
        submitData.id = businessId.value
      }
      const request = isEdit.value
        ? updateArticle(props.article.id, submitData)
        : createArticle(submitData)
        
      request.then(() => {
        loading.value = false
        ElMessage.success(isEdit.value ? '更新成功' : '创建成功')
        emit('success')
        handleClose()
      }).catch(() => {
        loading.value = false
      })
    } else {
      console.log('表单校验未通过', fields)
    }
  })
}
    
</script>

<template>
  <el-dialog :title="isEdit ? '编辑文章' : '新增文章'" v-model="dialogVisible" width="50%" @close="handleClose">
    <div>
      <el-form :model="formData" :rules="rules" ref="formRef" label-width="120px">
        <el-form-item label="文章标题" prop="title">
          <el-input v-model="formData.title" placeholder="请输入文章标题" maxlength="200" show-word-limit clearable />
        </el-form-item>
        <el-form-item label="所属分类" prop="categoryId">
          <el-select v-model="formData.categoryId" placeholder="请选择分类">
            <el-option v-for="item in props.categoryList" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="文章摘要" prop="summary">
          <el-input v-model="formData.summary" type="textarea" placeholder="请输入文章摘要(可选)" maxlength="1000" show-word-limit clearable :rows="4" />
        </el-form-item>
        <el-form-item label="标签" prop="tags">
          <el-select v-model="formData.tagArray" placeholder="请输入或选择文章标签" multiple filterable allow-create width="100%"> 
          <el-option v-for="item in commonTags" :key="item" :label="item" :value="item"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="封面图片">
          <div class="coverUpload">
            <el-upload
              class="avatar-uploader"
              action="#"
              :before-upload="beforeUpload"
              :http-request="handleUploadRequest"
              :show-file-list="false"
              accept="image/*"
            >
            <div v-if="!imgUrl" class="cover-placeholder">
              <p>点击上传封面</p>
            </div>
            <img v-else :src="imgUrl" class="cover-image" alt="封面图片" width="200px" height="140px" />
            </el-upload>
            <div v-if="imgUrl" class="cover-remove">
              <el-button type="danger" size="small" @click="removeCover">删除封面</el-button>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="文章内容" prop="content">
          <RichTextEditor
          v-model="formData.content"
          placeholder="请输入文章内容"
          :maxCharCount="5000"
          @change="handleContentChange"
          @created="handleEditorCreate"
          min-height="400px"
          />
        </el-form-item>
      </el-form>
      <div v-if="btnPreview">
        <h3>内容预览</h3>
        <div v-html="formData.content"></div>
      </div>
    </div>
    <template #footer>
      <el-button @click="btnPreview = !btnPreview">{{ btnPreview ? '隐藏效果' : '预览效果' }}</el-button>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" @click="handleSubmit" :loading="loading">{{ isEdit ? '更新文章' : '创建文章' }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped lang="scss">
.cover-placeholder{
  width: 200px;
  height: 120px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #8b949e;
  background: #f6f8fa;
}
</style>
