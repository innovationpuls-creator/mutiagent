# 教师端课程上传编辑与学生端 Branch 藤蔓路径融合实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在前端实现教师上传/编辑人培课程的闭环工作流，并在学生端 Branch 页面中以主干藤蔓与侧枝连线的形式融合展示人培课程和自主课程。

**Architecture:** 教师端采用单页内嵌状态机（Empty ➔ Loading ➔ Editor ➔ Error），以 `TreeTable` 结合 `DetailDrawer` 实现课程大纲录入并保存至 `localStorage`；学生端加载时拦截并合并本地保存的人培课程，在原有贝塞尔藤蔓的基础上将自主生成的课程挂接为侧枝，利用 SVG 高光连线呈现前导后续依赖。

**Tech Stack:** React 18, TypeScript, Framer Motion, Vitest, React Testing Library, Native CSS variables (OKLCH).

---

### Task 1: 契约类型扩展与 API 归一化层测试

**Files:**
- Modify: `frontend/src/types/branch.ts`
- Modify: `frontend/src/api/branch.ts`
- Create: `frontend/src/api/branch.test.ts`

- [ ] **Step 1: 扩展 BranchCourseNode 接口元数据类型**
  在 `frontend/src/types/branch.ts` 中新增可选的大纲、章节种子与时间编排属性：
  ```typescript
  // 在原本的 BranchCourseNode 接口中增加：
  export interface BranchCourseNode {
    course_node_id: string;
    course_or_chapter_theme: string;
    course_goal: string;
    status: BranchCourseStatus;
    has_outline: boolean;
    
    // 新增可选元数据
    is_custom?: boolean;
    parent_preset_id?: string;
    prerequisite_ids?: string[];
    time_arrangement?: {
      semester_scope: string;
      duration: string;
      pace_reason?: string;
    };
    key_points?: string[];
    difficult_points?: string[];
    acceptance_criteria?: string[];
  }
  ```

- [ ] **Step 2: 导出并重构 normalizeCourse 归一化方法**
  修改 `frontend/src/api/branch.ts`，导出 `normalizeCourse` 函数并补齐新增属性的解析逻辑：
  ```typescript
  export function normalizeCourse(value: unknown): BranchCourseNode {
    if (!isRecord(value)) {
      throw new Error('繁枝数据格式不正确');
    }
    const courseId = value.course_node_id;
    const theme = value.course_or_chapter_theme;
    const goal = value.course_goal;
    const status = value.status;
    const hasOutline = value.has_outline;
    if (
      typeof courseId !== 'string'
      || typeof theme !== 'string'
      || typeof goal !== 'string'
      || !isStatus(status)
      || typeof hasOutline !== 'boolean'
    ) {
      throw new Error('繁枝数据格式不正确');
    }
    
    const isCustom = typeof value.is_custom === 'boolean' ? value.is_custom : undefined;
    const parentPresetId = typeof value.parent_preset_id === 'string' ? value.parent_preset_id : undefined;
    const prerequisiteIds = Array.isArray(value.prerequisite_ids) && value.prerequisite_ids.every((id) => typeof id === 'string')
      ? (value.prerequisite_ids as string[])
      : undefined;
      
    let timeArrangement: BranchCourseNode['time_arrangement'] = undefined;
    if (isRecord(value.time_arrangement)) {
      const sem = value.time_arrangement.semester_scope;
      const dur = value.time_arrangement.duration;
      const pace = value.time_arrangement.pace_reason;
      if (typeof sem === 'string' && typeof dur === 'string') {
        timeArrangement = {
          semester_scope: sem,
          duration: dur,
          pace_reason: typeof pace === 'string' ? pace : undefined,
        };
      }
    }
    
    const keyPoints = Array.isArray(value.key_points) && value.key_points.every((kp) => typeof kp === 'string')
      ? (value.key_points as string[])
      : undefined;
    const difficultPoints = Array.isArray(value.difficult_points) && value.difficult_points.every((dp) => typeof dp === 'string')
      ? (value.difficult_points as string[])
      : undefined;
    const acceptanceCriteria = Array.isArray(value.acceptance_criteria) && value.acceptance_criteria.every((ac) => typeof ac === 'string')
      ? (value.acceptance_criteria as string[])
      : undefined;

    return {
      course_node_id: courseId,
      course_or_chapter_theme: theme,
      course_goal: goal,
      status,
      has_outline: hasOutline,
      is_custom: isCustom,
      parent_preset_id: parentPresetId,
      prerequisite_ids: prerequisiteIds,
      time_arrangement: timeArrangement,
      key_points: keyPoints,
      difficult_points: difficultPoints,
      acceptance_criteria: acceptanceCriteria,
    };
  }
  ```

- [ ] **Step 3: 编写 normalizeCourse 单元测试**
  新建 `frontend/src/api/branch.test.ts` 文件，添加对 `normalizeCourse` 功能的直接测试：
  ```typescript
  import { describe, it, expect } from 'vitest';
  import { normalizeCourse } from './branch';

  describe('normalizeCourse', () => {
    it('should parse minimal course correctly', () => {
      const raw = {
        course_node_id: 'math_101',
        course_or_chapter_theme: 'College Math',
        course_goal: 'Learn basics of calculus',
        status: 'locked',
        has_outline: false,
      };
      const result = normalizeCourse(raw);
      expect(result.course_node_id).toBe('math_101');
      expect(result.status).toBe('locked');
      expect(result.is_custom).toBeUndefined();
    });

    it('should parse full custom metadata correctly', () => {
      const raw = {
        course_node_id: 'python_101',
        course_or_chapter_theme: 'Python Intro',
        course_goal: 'Intro to programming',
        status: 'current',
        has_outline: true,
        is_custom: true,
        parent_preset_id: 'cs_basics',
        prerequisite_ids: ['math_101'],
        time_arrangement: {
          semester_scope: '1',
          duration: '32学时',
          pace_reason: 'First year first term',
        },
        key_points: ['Variables', 'Loops'],
        difficult_points: ['Recursion'],
        acceptance_criteria: ['Write a script'],
      };
      const result = normalizeCourse(raw);
      expect(result.is_custom).toBe(true);
      expect(result.parent_preset_id).toBe('cs_basics');
      expect(result.prerequisite_ids).toEqual(['math_101']);
      expect(result.time_arrangement?.semester_scope).toBe('1');
      expect(result.key_points).toContain('Loops');
    });

    it('should throw error on invalid format', () => {
      const raw = {
        course_node_id: 123, // 应该是 string
        course_or_chapter_theme: 'Python Intro',
        course_goal: 'Intro to programming',
        status: 'invalid_status',
        has_outline: true,
      };
      expect(() => normalizeCourse(raw)).toThrow('繁枝数据格式不正确');
    });
  });
  ```

- [ ] **Step 4: 运行 Vitest 测试验证 API 解析层**
  Run: `cd frontend && npx vitest run src/api/branch.test.ts`
  Expected: All 3 tests passed.

- [ ] **Step 5: 提交更改**
  ```bash
  git add frontend/src/types/branch.ts frontend/src/api/branch.ts frontend/src/api/branch.test.ts
  git commit -m "feat: add metadata to BranchCourseNode and implement normalizeCourse parser"
  ```

---

### Task 2: 教师工作台组件与状态机开发

**Files:**
- Modify: `frontend/src/pages/teacher/TeacherPage.tsx`
- Modify: `frontend/src/pages/teacher/teacher.css`

- [ ] **Step 1: 定义完整 8 门必修课程大纲 Mock 数据生成器**
  在 `TeacherPage.tsx` 中编写辅助生成大一至大四（学期 1 到 8）完整人培课程的静态数据：
  ```typescript
  const MOCK_TEACHER_COURSES: BranchCourseNode[] = [
    {
      course_node_id: 'math_1',
      course_or_chapter_theme: '高等数学 I',
      course_goal: '掌握微积分基本计算与极限理论',
      status: 'locked',
      has_outline: false,
      is_custom: false,
      time_arrangement: { semester_scope: '1', duration: '64学时/4学分' },
      key_points: ['极限与连续', '导数与微分', '一元函数积分学'],
      difficult_points: ['微分中值定理证明', '不定积分换元法'],
      acceptance_criteria: ['完成所有课后习题', '期末卷面成绩达标'],
    },
    {
      course_node_id: 'python_1',
      course_or_chapter_theme: 'Python 程序设计',
      course_goal: '学习编程基础，掌握基本控制流与数据结构',
      status: 'locked',
      has_outline: false,
      is_custom: false,
      time_arrangement: { semester_scope: '1', duration: '48学时/3学分' },
      key_points: ['数据类型', '条件与循环', '函数与模块'],
      difficult_points: ['递归函数调用', '文件异常处理'],
      acceptance_criteria: ['独立编写期末大作业', '实验报告合格'],
    },
    {
      course_node_id: 'algebra_1',
      course_or_chapter_theme: '线性代数',
      course_goal: '掌握矩阵论、行列式与线性空间变换',
      status: 'locked',
      has_outline: false,
      is_custom: false,
      time_arrangement: { semester_scope: '2', duration: '48学时/3学分' },
      key_points: ['行列式计算', '矩阵特征值', '线性方程组通解'],
      difficult_points: ['二次型正定性证明', '正交变换矩阵'],
      acceptance_criteria: ['通过期末统一闭卷笔试'],
    },
    {
      course_node_id: 'ds_1',
      course_or_chapter_theme: '数据结构',
      course_goal: '掌握常用线性及非线性数据结构的实现与算法复杂度分析',
      status: 'locked',
      has_outline: false,
      is_custom: false,
      prerequisite_ids: ['python_1'],
      time_arrangement: { semester_scope: '3', duration: '64学时/4学分' },
      key_points: ['链表与栈', '二叉树与哈夫曼编码', '图的深度优先遍历'],
      difficult_points: ['AVL树旋转', 'Dijkstra 最短路径算法'],
      acceptance_criteria: ['通过在线 OJ 测试', '编写课程大作业'],
    },
    {
      course_node_id: 'comp_org_1',
      course_or_chapter_theme: '计算机组成原理',
      course_goal: '了解微型计算机内部硬件架构与运算器、控制器基本工作流程',
      status: 'locked',
      has_outline: false,
      is_custom: false,
      time_arrangement: { semester_scope: '4', duration: '64学时/4学分' },
      key_points: ['补码加减运算', 'Cache 命中机制', 'CPU 指令周期寻址'],
      difficult_points: ['微程序控制器微指令设计', '流水线冒险规避'],
      acceptance_criteria: ['期末设计 CPU 微控制器实验通过'],
    },
    {
      course_node_id: 'se_1',
      course_or_chapter_theme: '软件工程',
      course_goal: '掌握传统与敏捷项目管理研发流程与 UML 统一建模语言',
      status: 'locked',
      has_outline: false,
      is_custom: false,
      time_arrangement: { semester_scope: '5', duration: '48学时/3学分' },
      key_points: ['需求工程规约', '软件测试策略', '敏捷 Sprint 迭代规划'],
      difficult_points: ['用例图与时序图设计', '设计模式实战应用'],
      acceptance_criteria: ['按小组编写并答辩完整软件工程项目文档'],
    },
    {
      course_node_id: 'os_1',
      course_or_chapter_theme: '操作系统',
      course_goal: '理解进程调度、死锁避免、虚拟内存页替换以及文件系统实现',
      status: 'locked',
      has_outline: false,
      is_custom: false,
      prerequisite_ids: ['ds_1'],
      time_arrangement: { semester_scope: '6', duration: '64学时/4学分' },
      key_points: ['多线程同步信号量', '银行家算法', '虚拟内存页表置换'],
      difficult_points: ['生产者消费者PV操作实现', '磁盘调度与索引节点'],
      acceptance_criteria: ['完成进程调度模拟器代码验收'],
    },
    {
      course_node_id: 'grad_intern_1',
      course_or_chapter_theme: '毕业实习',
      course_goal: '进入企业进行软件研发工程实习，完成实习周记与总结报告',
      status: 'locked',
      has_outline: false,
      is_custom: false,
      time_arrangement: { semester_scope: '8', duration: '128学时/8学分' },
      key_points: ['行业研发体系认知', '团队协同开发', '生产环境部署规范'],
      difficult_points: ['真实生产环境 Bug 线上排查与处理'],
      acceptance_criteria: ['提交企业盖章实习证明及 10 篇实习周记'],
    },
  ];
  ```

- [ ] **Step 2: 实现状态机核心逻辑与 UI 框架**
  重构 `TeacherPage.tsx`，支持 `empty` | `loading` | `editor` | `error` 状态管理、输入文件验证与 `localStorage` 保存：
  ```typescript
  // 使用 React state 管理页面核心状态
  const [pageState, setPageState] = useState<TeacherPageState>('empty');
  const [fileError, setFileError] = useState<string | null>(null);
  const [courses, setCourses] = useState<BranchCourseNode[]>([]);
  const [activeCourseId, setActiveCourseId] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  ```

- [ ] **Step 3: 编写 UploadZone 与 Loading 动画**
  - **UploadZone 逻辑**：仅接收 `.pdf`, `.docx`, `.doc`, `.txt`, `.png`, `.jpg`, `.jpeg` 且大小 `<= 20MB`。
  - **BreathingLoader 动效**：使用 Framer Motion 的 `animate` 实现低频缩放，使用 CSS 动画实现光晕渐变循环，匹配 `var(--ease-breathe)` 与 `var(--duration-breathe)`。
  - 模拟识别定时器（3000ms）完成后，调用 `setCourses(MOCK_TEACHER_COURSES)` 切换至 `editor`。

- [ ] **Step 4: 编写 TreeTable (左表) 与 DetailDrawer (右滑抽屉) 组件**
  - **TreeTable**：按大一到大四（学期 1 到 8）折叠渲染行。
  - **DetailDrawer**：使用 `AnimatePresence` 挂载，滑动使用 `transition={motionTokens.lazy}`，即 `{ duration: 0.42, ease: [0.33, 1, 0.68, 1] }`，避免 spring 导致晃动过冲。抽屉中各字段（课程名、学时、课程目标等）绑定 `onChange` 逻辑更新本地 `courses` 状态。
  - **保存**：点击“保存并发布”时执行：
    ```typescript
    localStorage.setItem('teacher_cultivation_program', JSON.stringify(courses));
    setToastMessage('人培方案已成功发布并对齐！');
    ```

- [ ] **Step 5: 编写样式表 `teacher.css` 对齐设计系统**
  在 `frontend/src/pages/teacher/teacher.css` 中，背景使用 `var(--color-background)`，字体使用 `LXGW WenKai`，抽屉和卡片阴影严格使用 `var(--shadow-md)` 与 `var(--shadow-lg)`。

- [ ] **Step 6: 提交更改**
  ```bash
  git add frontend/src/pages/teacher/TeacherPage.tsx frontend/src/pages/teacher/teacher.css
  git commit -m "feat: implement TeacherPage multi-state wizard and DetailDrawer editor"
  ```

---

### Task 3: 教师端页面状态机测试

**Files:**
- Create: `frontend/src/pages/teacher/TeacherPage.test.tsx`

- [ ] **Step 1: 编写 TeacherPage 测试套件**
  在 `frontend/src/pages/teacher/TeacherPage.test.tsx` 中创建测试验证文件校验、页面转场和本地数据持久化（保存密钥为 `teacher_cultivation_program`）：
  ```typescript
  import { describe, it, expect, vi, beforeEach } from 'vitest';
  import { render, screen, fireEvent, waitFor } from '@testing-library/react';
  import { TeacherPage } from './TeacherPage';

  // Mock React Router and AuthContext
  vi.mock('../../contexts/AuthContext', () => ({
    useAuth: () => ({ user: { username: '测试教师' } }),
  }));

  describe('TeacherPage State Machine', () => {
    beforeEach(() => {
      localStorage.clear();
      vi.useFakeTimers();
    });

    it('renders empty state initially', () => {
      render(<TeacherPage />);
      expect(screen.getByText('拖拽或点击上传培养方案文档')).toBeInTheDocument();
    });

    it('displays error state when uploading large file', () => {
      render(<TeacherPage />);
      const file = new File(['a'.repeat(21 * 1024 * 1024)], 'curriculum.pdf', { type: 'application/pdf' });
      const dropzone = screen.getByTestId('dropzone');
      
      fireEvent.drop(dropzone, { dataTransfer: { files: [file] } });
      expect(screen.getByText('文件大小超出20MB上限')).toBeInTheDocument();
    });

    it('advances empty -> loading -> editor on valid file drop', async () => {
      render(<TeacherPage />);
      const file = new File(['dummy content'], 'curriculum.pdf', { type: 'application/pdf' });
      const dropzone = screen.getByTestId('dropzone');
      
      fireEvent.drop(dropzone, { dataTransfer: { files: [file] } });
      expect(screen.getByText(/正在读取培养方案并由AI对齐大纲/)).toBeInTheDocument();

      // 快进 3 秒模拟识别时间
      vi.advanceTimersByTime(3000);

      await waitFor(() => {
        expect(screen.getByText('大一 (Freshman)')).toBeInTheDocument();
        expect(screen.getByText('高等数学 I')).toBeInTheDocument();
      });
    });

    it('opens DetailDrawer and saves update to localStorage', async () => {
      render(<TeacherPage />);
      const file = new File(['dummy content'], 'curriculum.pdf', { type: 'application/pdf' });
      const dropzone = screen.getByTestId('dropzone');
      
      fireEvent.drop(dropzone, { dataTransfer: { files: [file] } });
      vi.advanceTimersByTime(3000);

      const courseRow = await screen.findByText('高等数学 I');
      fireEvent.click(courseRow);

      const goalInput = screen.getByLabelText('课程目标');
      fireEvent.change(goalInput, { target: { value: '全新的微积分课程目标' } });

      const saveButton = screen.getByText('保存并发布');
      fireEvent.click(saveButton);

      // 验证已使用正确的键：teacher_cultivation_program
      const savedData = JSON.parse(localStorage.getItem('teacher_cultivation_program') || '[]');
      expect(savedData[0].course_goal).toBe('全新的微积分课程目标');
    });
  });
  ```

- [ ] **Step 2: 运行 TeacherPage 交互测试**
  Run: `cd frontend && npx vitest run src/pages/teacher/TeacherPage.test.tsx`
  Expected: PASS

- [ ] **Step 3: 提交更改**
  ```bash
  git add frontend/src/pages/teacher/TeacherPage.test.tsx
  git commit -m "test: add TeacherPage state transition and localStorage save tests"
  ```

---

### Task 4: 学生端 Branch 页面数据桥接与侧枝融合

**Files:**
- Modify: `frontend/src/pages/branch/BranchPage.tsx`
- Modify: `frontend/src/pages/branch/branch.css`

- [ ] **Step 1: 实现 localStorage 数据融合规则**
  在 `BranchPage.tsx` 的 `loadOverview` / `fetchBranchOverview` 调用后，加入本地人培大纲的合并逻辑，合并密钥统一为 `teacher_cultivation_program`：
  ```typescript
  const storedProgram = localStorage.getItem('teacher_cultivation_program');
  if (storedProgram) {
    const presetCourses: BranchCourseNode[] = JSON.parse(storedProgram);
    presetCourses.forEach((preset) => {
      // 1. 映射 semester_scope 到年级槽位
      const sem = parseInt(preset.time_arrangement?.semester_scope || '1', 10);
      let yearId: YearId = 'year_1';
      if (sem >= 7) yearId = 'year_4';
      else if (sem >= 5) yearId = 'year_3';
      else if (sem >= 3) yearId = 'year_2';

      const year = overview.years[yearId];
      if (year) {
        // 2. ID 去重与元数据合并规则
        const existIdx = year.courses.findIndex((c) => c.course_node_id === preset.course_node_id);
        if (existIdx >= 0) {
          year.courses[existIdx] = {
            ...preset,
            ...year.courses[existIdx], // API 返回数据字段优先
            key_points: preset.key_points,
            difficult_points: preset.difficult_points,
            acceptance_criteria: preset.acceptance_criteria,
          };
        } else {
          year.courses.push(preset);
        }
        year.has_courses = true;
        year.is_clickable = true;
      }
    });
  }
  ```

- [ ] **Step 2: 改造状态联动与解锁机制**
  在 `BranchPage.tsx` 渲染每个节点卡片时，更新解锁判断条件：
  ```typescript
  function resolveUnlockedStatus(course: BranchCourseNode, allCourses: BranchCourseNode[]): BranchCourseStatus {
    if (course.status === 'completed') return 'completed';
    
    if (course.is_custom && course.parent_preset_id) {
      const parent = allCourses.find((c) => c.course_node_id === course.parent_preset_id);
      if (parent && parent.status === 'completed' && course.status === 'locked') {
        // 父节点已完成，且原始状态为 locked，在渲染态提升为 current，子节点不能自动升级为 completed
        return 'current';
      }
    }
    return course.status;
  }
  ```

- [ ] **Step 3: 自定义分叉课程卡片与发光粒子视觉微调 (CSS)**
  在 `branch.css` 中增加对自定义课程节点的视觉差异化表现，使用 `--space-8` 替换任意硬编码尺寸：
  ```css
  .branch-blob-card-custom {
    background: var(--color-primary-soft);
    border: 2px dashed var(--color-primary);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-sm);
  }
  
  .branch-custom-glow-dot {
    inline-size: var(--space-8);
    block-size: var(--space-8);
    border-radius: var(--radius-full);
    background: var(--color-primary);
    box-shadow: var(--shadow-glow);
  }
  ```

- [ ] **Step 4: 提交更改**
  ```bash
  git add frontend/src/pages/branch/BranchPage.tsx frontend/src/pages/branch/branch.css
  git commit -m "feat: merge localStorage preset program and style custom branch nodes in BranchPage"
  ```

---

### Task 5: 前导高光连线渲染

**Files:**
- Modify: `frontend/src/pages/branch/BranchPage.tsx`

- [ ] **Step 1: 点击课程渲染 SVG 拓扑依赖高光连线**
  修改 `PathSession` 中的 SVG 渲染段。当存在选中课程节点 `focusedCourseId` 时，寻找对应课程的前置或定制关系：
  ```typescript
  const selectedCourse = courses.find((c) => c.course_node_id === focusedCourseId);
  const connectionPaths: string[] = [];
  if (selectedCourse) {
    if (selectedCourse.prerequisite_ids) {
      selectedCourse.prerequisite_ids.forEach((preId) => {
        const preNode = courses.find((c) => c.course_node_id === preId);
        if (preNode) {
          const pathD = generateBezierConnectionPath(preNode, selectedCourse);
          connectionPaths.push(pathD);
        }
      });
    }
    if (selectedCourse.is_custom && selectedCourse.parent_preset_id) {
      const parentNode = courses.find((c) => c.course_node_id === selectedCourse.parent_preset_id);
      if (parentNode) {
        const pathD = generateBezierConnectionPath(parentNode, selectedCourse);
        connectionPaths.push(pathD);
      }
    }
  }
  ```

- [ ] **Step 2: 渲染高光路径 SVG 元素**
  在 SVG 幕布中通过 `connectionPaths.map` 输出高光路径。描边使用主高亮色 `oklch(76% 0.12 55 / 0.85)`，宽度为 `3px`，过渡平滑。

- [ ] **Step 3: 提交更改**
  ```bash
  git add frontend/src/pages/branch/BranchPage.tsx
  git commit -m "feat: implement SVG Bezier highlighting for prerequisites and custom branch connections"
  ```

---

### Task 6: 学生端 Branch 融合与高光集成测试

**Files:**
- Modify: `frontend/src/pages/branch/BranchPage.test.tsx`

- [ ] **Step 1: 编写带人培 LocalStorage 劫持的集成测试**
  由于原测试 `renderBranchPage` 会对全局 `localStorage` 进行 Stub 挂载且默认过滤屏蔽非身份认证 key，我们必须在测试文件中新增一个专门用于注入人培大纲的测试辅助渲染器 `renderBranchPageWithCultivation(mockProgram)`。
  测试数据必须包含 `course_goal` 和 `has_outline` 等必填字段，以防止 TypeScript 类型检查和运行时失败。
  在 `frontend/src/pages/branch/BranchPage.test.tsx` 顶部或辅助函数区新增：
  ```typescript
  function renderBranchPageWithCultivation(mockPreset: BranchCourseNode[]) {
    vi.stubGlobal('localStorage', {
      getItem: vi.fn((key: string) => {
        if (key === 'teacher_cultivation_program') {
          return JSON.stringify(mockPreset);
        }
        if (key !== 'mutiagent-auth') {
          return null;
        }
        return JSON.stringify({
          token: 'token-1',
          user: {
            uid: 'user-1',
            username: '测试用户',
            identifier: 'user@example.com',
            provider: 'password',
            is_active: true,
            created_at: '2026-06-02T00:00:00Z',
            last_login_at: null,
          },
        });
      }),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    });

    return render(
      <AuthProvider>
        <AiWidgetProvider>
          <MemoryRouter>
            <BranchPage />
          </MemoryRouter>
        </AiWidgetProvider>
      </AuthProvider>,
    );
  }
  ```

- [ ] **Step 2: 编写集成测试用例**
  在 `frontend/src/pages/branch/BranchPage.test.tsx` 的 `describe('BranchPage', ...)` 块内增加两个具体用例，验证人培数据的合并算法及自主生成卡片的解锁样式：
  ```typescript
  describe('BranchPage Integration with Local Cultivation Program', () => {
    it('merges preset program from localStorage and overrides has_courses', async () => {
      const mockPreset: BranchCourseNode[] = [
        {
          course_node_id: 'custom_math_99',
          course_or_chapter_theme: '高等数学 IX',
          course_goal: '高等数学 IX 课程目标，掌握数学分析基础',
          status: 'locked',
          has_outline: false,
          time_arrangement: { semester_scope: '1', duration: '32学时' },
        }
      ];
      
      // 使用带注入的测试辅助函数挂载
      renderBranchPageWithCultivation(mockPreset);
      
      await waitFor(() => {
        expect(screen.getByText('高等数学 IX')).toBeInTheDocument();
      });
    });

    it('integrates custom nodes with proper unlock status and classes', async () => {
      const mockCustomPreset: BranchCourseNode[] = [
        {
          course_node_id: 'preset_ds_1',
          course_or_chapter_theme: '普通课程',
          course_goal: '学习结构与算法',
          status: 'completed',
          has_outline: true,
          is_custom: false,
          time_arrangement: { semester_scope: '3', duration: '64学时' },
        },
        {
          course_node_id: 'custom_graph_1',
          course_or_chapter_theme: '自主生成图论课程',
          course_goal: '深入掌握网络与图的遍历',
          status: 'locked',
          has_outline: false,
          is_custom: true,
          parent_preset_id: 'preset_ds_1',
          time_arrangement: { semester_scope: '3', duration: '32学时' },
        }
      ];
      
      renderBranchPageWithCultivation(mockCustomPreset);
      
      await waitFor(() => {
        const customCard = screen.getByText('自主生成图论课程').closest('button');
        expect(customCard).toBeInTheDocument();
        // 验证由于 parent 完成，locked 状态的侧枝在渲染态被提升为 current 进行中
        expect(screen.getByText('进行中')).toBeInTheDocument();
      });
    });
  });
  ```

- [ ] **Step 3: 运行全部繁枝测试验证实现**
  Run: `cd frontend && npm run test`
  Expected: PASS

- [ ] **Step 4: 提交更改**
  ```bash
  git add frontend/src/pages/branch/BranchPage.test.tsx
  git commit -m "test: verify BranchPage data merging, custom card rendering, and connections"
  ```
