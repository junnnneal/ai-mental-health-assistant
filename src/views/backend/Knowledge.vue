<script setup lang="ts">
import PageHead from "@/components/backend/PageHead.vue";
import TableSearch from "@/components/backend/TableSearch.vue";
import { categoryTree, articlePage } from "@/apis/admin";
import { ref, onMounted, reactive } from "vue";
import ArticleDialog from "@/components/backend/ArticleDialog.vue";
import { getArticleDetail } from "@/apis/admin";
import { ElMessage } from "element-plus";
import { ElMessageBox } from "element-plus";
import { publishArticle, deleteArticle } from "@/apis/admin";

//分类映射
const categoryOptions = reactive<any>({});
//分类列表
const categoryList = ref<any>([]);
//分页参数
const pagination = ref<any>({
  currentPage: 1,
  size: 10,
  total: 0,
});
//列表数据
const articleList = ref<any>([]);
//新增文章弹窗是否显示
const dialogVisible = ref(false);
//新增文章弹窗表单数据
const formItem = ref([
  {
    label: "文章标题",
    prop: "title",
    comp: "input",
    placeholder: "请输入文章标题",
  },
  {
    label: "文章分类",
    prop: "categoryId",
    comp: "select",
    placeholder: "请选择文章分类",
  },
  {
    label: "状态",
    prop: "status",
    comp: "select",
    placeholder: "请选择状态",
    options: [
      {
        label: "全部",
        value: "",
      },
      {
        label: "草稿",
        value: "0",
      },
      {
        label: "已发布",
        value: "1",
      },
      {
        label: "已下线",
        value: "2",
      },
    ],
  },
]);
//当前文章详情
const currentArticle = ref<any>(null);

const handleSearch = async (formData: any) => {
  const params = {
    ...pagination.value,
    ...formData,
  };
  const res = await articlePage(params);
  articleList.value = res.records;
  pagination.value.total = res.total || res.pages * pagination.value.size;
};

//分页改变时触发
const handleChange = (page: number) => {
  pagination.value.currentPage = page;
  handleSearch({});
};

//新增文章成功后，刷新列表
const handelSuccess = () => {
  //取消弹窗
  dialogVisible.value = false;
  handleSearch({});
};

//编辑文章
const handleEdit = (row: any) => {
  console.log(row);
  if (!row.id) {
    //新增文章
    dialogVisible.value = true;
    currentArticle.value = null;
  } else {
    //编辑文章
    getArticleDetail(row.id).then((res) => {
      console.log(res);
      currentArticle.value = res;
      dialogVisible.value = true;
    });
  }
};
//发布文章
const handlePublish = (row: any) => {
  //提示,点确定进入第一个then,接口正常是第二个then
  ElMessageBox.confirm(`确认发布文章${row.title}吗？`, "发布确认", {
    confirmButtonText: "确定发布",
    cancelButtonText: "取消",
    type: "primary",
  })
    .then(() => {
      publishArticle(row.id, { status: 1 }).then((res) => {
        ElMessage.success("发布成功");
        //刷新列表
        handleSearch({});
      });
    })
    .catch(() => {
      ElMessage({
        type: "info",
        message: "已取消发布",
      });
    });
  console.log(row);
};
//下线文章
const handleDown = (row: any) => {
  //提示,点确定进入第一个then,接口正常是第二个then
  ElMessageBox.confirm(`确认下线文章${row.title}吗？`, "下线确认", {
    confirmButtonText: "确定下线",
    cancelButtonText: "取消",
    type: "warning",
  })
    .then(() => {
      publishArticle(row.id, { status: 2 }).then((res) => {
        ElMessage.success("下线成功");
        //刷新列表
        handleSearch({});
      });
    })
    .catch(() => {
      ElMessage({
        type: "info",
        message: "已取消下线",
      });
    });
  console.log(row);
};
//删除文章
const handleDelete = (row: any) => {
  ElMessageBox.confirm(`确认删除文章${row.title}吗？`, "删除确认", {
    confirmButtonText: "确定删除",
    cancelButtonText: "取消",
    type: "warning",
  })
    .then(() => {
      deleteArticle(row.id).then((res) => {
        ElMessage.success("删除成功");
        //刷新列表
        handleSearch({});
      });
    })
    .catch(() => {
      ElMessage({
        type: "info",
        message: "已取消删除",
      });
    });
  console.log(row);
};

onMounted(async () => {
  const res = await categoryTree();
  //响应拦截器已经解包数据了，不需要.data
  categoryList.value = res.map((item: any) => {
    //做映射处理，将id作为key，categoryName作为value
    categoryOptions[item.id] = item.categoryName;
    console.log(item);
    return {
      label: item.categoryName,
      value: item.id,
    };
  });
  //包一层if，防止formItem.value[1]不存在
  if (formItem.value[1]) {
    formItem.value[1].options = categoryList.value;
  }
  //默认搜索
  handleSearch({});
});
</script>

<template>
  <div>
    <PageHead title="知识文章">
      <!-- 具名插槽的使用 -->
      <template #buttons>
        <el-button @click="handleEdit({})" type="primary">新增</el-button>
        <el-button type="primary">删除</el-button>
      </template>
    </PageHead>
    <TableSearch :formItem="formItem" @search="handleSearch" />
    <!-- 渲染数据 -->
    <el-table :data="articleList" style="width: 100%; margin-top: 25px">
      <el-table-column label="文章标题" fixed="left">
        <template #default="scope">
          <div style="display: flex; align-items: center">
            <el-icon><timer /></el-icon>
            <span>{{ scope.row.title }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="分类" width="200">
        <template #default="scope">
          <div style="display: flex; align-items: center">
            <el-icon><timer /></el-icon>
            <span>{{ categoryOptions[scope.row.categoryId] }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="authorName" label="作者" width="150" />
      <el-table-column prop="readCount" label="阅读量" width="150" />
      <el-table-column prop="updatedAt" label="发布时间" width="260" />
      <el-table-column label="操作" width="230" fixed="right">
        <template #default="scope">
          <el-button text type="primary" @click="handleEdit(scope.row)"
            >编辑</el-button
          >
          <el-button
            @click="handlePublish(scope.row)"
            v-if="scope.row.status === 0 || scope.row.status === 2"
            text
            type="success"
            >发布</el-button
          >
          <el-button
            @click="handleDown(scope.row)"
            v-if="scope.row.status === 1"
            text
            type="warning"
            >下线</el-button
          >
          <el-button @click="handleDelete(scope.row)" text type="danger"
            >删除</el-button
          >
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <el-pagination
      layout="prev, pager, next"
      :total="pagination.total"
      :page-size="pagination.size"
      @change="handleChange"
      style="margin-top: 25px"
    />

    <!-- 新增文章弹窗 -->
    <!-- 通过v-model:modelValue双向绑定dialogVisible，实现弹窗显示和隐藏
       这里的v-model:modelValue就是update:modelValue事件 -->
    <ArticleDialog
      v-model:modelValue="dialogVisible"
      :categoryList="categoryList"
      :article="currentArticle"
      @success="handelSuccess"
    />
  </div>
</template>
