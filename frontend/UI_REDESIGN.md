# Novel Studio Gemini - UI重设计文档

## 概述

全新设计的AI小说创作界面,专为长篇网络小说创作优化,提供沉浸式的写作体验和强大的AI协作功能。

## 新架构特性

### 1. 三栏布局设计

```
┌─────────────────────────────────────────────────────────────┐
│                    顶部导航栏 (Header)                        │
├──────────┬────────────────────────────┬────────────────────┤
│          │                            │                    │
│  章节    │     写作工作室              │   AI助手面板       │
│  列表    │   (WritingStudio)          │  (AIAssistant)     │
│          │                            │                    │
│ Chapter  │  - 章节导航                 │  - Agent状态      │
│ Sidebar  │  - 大纲显示                 │  - 角色信息       │
│          │  - 编辑器                   │  - 质量指标       │
│ (280px)  │  - AI进度条                 │                    │
│          │                            │   (384px)          │
└──────────┴────────────────────────────┴────────────────────┘
```

### 2. 核心组件

#### 2.1 WritingStudio (写作工作室)
**位置**: 中央主要区域
**功能**:
- **章节导航**: 快速切换上下章节
- **AI状态指示器**: 实时显示当前执行的Agent (Director/Editor/Writer等)
- **大纲区域**: 可折叠的章节大纲显示,支持在线编辑
- **主编辑器**: 大字号、serif字体的沉浸式编辑体验
- **AI进度条**: 底部显示6个Agent的执行进度

**特色**:
- 自动保存机制
- 空状态引导 (未生成章节时显示引导界面)
- 实时轮询工作流状态 (3秒间隔)

#### 2.2 ChapterSidebar (章节侧边栏)
**位置**: 左侧
**功能**:
- **章节列表**: 显示所有章节及其状态 (已完成/草稿/错误/空白)
- **搜索功能**: 快速查找特定章节
- **新建章节**: 一键创建新章节
- **统计面板**: 显示已完成、草稿、总计章节数

**状态标识**:
- 🟢 已完成: 绿色边框
- 🟡 草稿: 黄色边框
- 🔴 错误: 红色边框
- ⚪ 空白: 灰色边框

#### 2.3 AIAssistantPanel (AI助手面板)
**位置**: 右侧
**功能**:
- **Agents Tab**: 显示6个Agent的实时状态和进度
  - Director: 战略规划
  - Editor: 大纲编排
  - Writer: 内容撰写
  - Simulator: 逻辑验证
  - Reviewer: 质量审查
  - Archivist: 数据归档

- **角色 Tab**: 显示活跃角色列表
  - 名称、境界、动机
  - 物品清单预览

- **指标 Tab**: 质量评估指标
  - 剧情逻辑分数 (蓝色)
  - 风格一致性分数 (紫色)
  - 物理规则违规 (绿色/红色)
  - 张力值 (红色)

#### 2.4 WorldPanel (世界观管理面板)
**位置**: 模态弹窗
**触发**: 点击顶部导航栏"世界观"按钮
**功能**:
- **知识图谱**: 嵌入KnowledgeGraph组件
- **角色库**: 双栏布局
  - 左侧: 角色列表
  - 右侧: 详细信息 (动机/外貌/黄金人格锚点/物品/关系)
- **物品系统**: (开发中)
- **世界设定**: (开发中)

### 3. 顶部导航栏功能

```
[Logo] Novel Studio | AI-Powered Creative Writing
                                    [世界观] [导出] | [🌙] [⚙️] [☰]
```

- **世界观**: 打开WorldPanel模态窗口
- **导出**: 打开ExportModal (TXT/EPUB)
- **夜间模式**: 切换Dark Mode (已实现状态,样式待完善)
- **设置**: (预留)
- **折叠菜单**: 在移动端显示

### 4. 紧急干预机制

当Simulator连续3次拒绝后,触发`intervention_reason`状态:

```
┌──────────────────────────────────────────────────────────────┐
│ ⚠️ Logic Deadlock - Human Intervention Required             │
│                                                              │
│ 原因: [具体的逻辑冲突描述]                                     │
│                                                              │
│ [FORCE PASS]  [FIX IN WORLD PANEL]  [DISMISS]               │
└──────────────────────────────────────────────────────────────┘
```

位于屏幕底部,红色警告条,提供3种处理方式:
1. 强制通过 (忽略逻辑)
2. 前往世界观面板修正
3. 忽略警告

## API集成

### 使用的后端Endpoints

```typescript
// 工作流控制
POST /api/workflow/start         // 启动章节生成
POST /api/workflow/resume        // 继续执行
POST /api/workflow/update        // 更新状态 (上帝模式)
GET  /api/workflow/{num}/state   // 获取状态

// 数据查询
GET  /api/characters             // 获取角色列表
POST /api/characters/{name}/update // 更新角色数据

// 导出
POST /api/export/generate        // 生成导出文件
GET  /api/export/download        // 下载文件

// 图谱
GET  /api/graph/visualize        // 获取知识图谱数据
GET  /api/graph/impact           // 获取影响子图
```

### 实时更新机制

所有组件使用 `useEffect` + `setInterval` 实现轮询:
- WritingStudio: 3秒轮询workflow状态
- ChapterSidebar: 首次加载时批量检查前20章
- AIAssistantPanel: 通过props接收workflow,自动响应变化

## 用户体验优化

### 1. 视觉层级
- **主编辑器**: 大字号serif字体,白色背景,充分留白
- **次要信息**: 小字号,灰色,不抢占注意力
- **状态指示**: 使用颜色编码 (蓝=执行中,绿=完成,灰=等待)

### 2. 交互反馈
- 所有按钮都有 hover 状态
- 执行中的Agent带有 `animate-pulse` 效果
- 加载状态使用 `Loader` 图标旋转动画

### 3. 响应式设计
- 桌面端: 完整三栏布局
- 平板/移动端:
  - 可折叠章节侧边栏
  - 可折叠AI助手面板
  - 顶部导航栏自适应

### 4. 信息密度控制
- 章节列表: 仅显示核心信息 (编号/状态/字数)
- AI面板: 使用Tab切换,避免信息过载
- 编辑器: 无干扰模式,专注写作

## 颜色系统

```css
/* 品牌色 */
Primary:   #3B82F6 (blue-600)   - 主要操作按钮
Secondary: #8B5CF6 (purple-600) - 强调色

/* 功能色 */
Success:   #10B981 (green-600)  - 完成状态
Warning:   #F59E0B (yellow-600) - 警告/草稿
Error:     #EF4444 (red-600)    - 错误/紧急

/* Agent专属色 */
Director:  #A855F7 (purple-500)
Editor:    #3B82F6 (blue-500)
Writer:    #F59E0B (yellow-500)
Simulator: #10B981 (green-500)
Reviewer:  #6366F1 (indigo-500)
Archivist: #6B7280 (gray-500)
```

## 待完善功能

- [ ] 暗黑模式完整样式支持
- [ ] 章节标题自动提取和显示
- [ ] 自动保存debounce优化
- [ ] 物品系统面板实现
- [ ] 世界设定面板实现
- [ ] 章节导出单独下载
- [ ] 快捷键支持 (Ctrl+S保存, Ctrl+G生成等)
- [ ] 撤销/重做功能
- [ ] 版本历史记录
- [ ] 协作编辑冲突处理

## 技术栈

- **React 19**: 主框架
- **TypeScript**: 类型安全
- **Tailwind CSS**: 样式系统
- **Lucide React**: 图标库
- **Axios**: HTTP请求
- **React Force Graph**: 知识图谱可视化

## 启动方式

```bash
# 后端
cd backend
uv run uvicorn api.main:app --reload

# 前端
cd frontend
npm run dev
```

访问 `http://localhost:5173` 查看新界面。

## 设计理念

1. **以创作者为中心**: 编辑器占据最大空间,减少干扰
2. **AI透明化**: 实时显示AI工作状态,让创作者了解幕后过程
3. **快速迭代**: 一键生成,快速预览,即时修改
4. **数据可视化**: 通过图谱和指标让复杂的世界观变得可管理
5. **安全网机制**: 紧急干预系统防止AI陷入死循环

---

**更新日期**: 2026-01-18
**设计者**: Claude Sonnet 4.5
