import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { LogOut } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { BranchCourseNode } from '../../types/branch';
import { OrganicCanvas, GraphNode, GraphEdge } from '../../components/graph/OrganicCanvas';
import './teacher.css';

export type TeacherPageState = 'empty' | 'loading' | 'editor' | 'error';

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
    time_arrangement: { semester_scope: '2', duration: '48学时/3学分' },
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
    time_arrangement: { semester_scope: '3', duration: '48学时/3学分' },
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
    time_arrangement: { semester_scope: '4', duration: '64学时/4学分' },
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
    time_arrangement: { semester_scope: '5', duration: '64学时/4学分' },
    key_points: ['补码加减运算', 'Cache 命中机制', 'CPU 指令周期寻址'],
    difficult_points: ['微程序控制器微指令设计', '流水线冒险规避'],
    acceptance_criteria: ['期末设计 CPU 微控制器实验通过'],
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
    course_node_id: 'se_1',
    course_or_chapter_theme: '软件工程',
    course_goal: '掌握传统与敏捷项目管理研发流程与 UML 统一建模语言',
    status: 'locked',
    has_outline: false,
    is_custom: false,
    time_arrangement: { semester_scope: '7', duration: '48学时/3学分' },
    key_points: ['需求工程规约', '软件测试策略', '敏捷 Sprint 迭代规划'],
    difficult_points: ['用例图与时序图设计', '设计模式实战应用'],
    acceptance_criteria: ['按小组编写并答辩完整软件工程项目文档'],
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

export const motionTokens = {
  lazy: { duration: 0.42, ease: [0.33, 1, 0.68, 1] },
} as const;

function getGradeName(semester: string): string {
  const sem = parseInt(semester, 10);
  if (sem <= 2) return '大一 (Freshman)';
  if (sem <= 4) return '大二 (Sophomore)';
  if (sem <= 6) return '大三 (Junior)';
  return '大四 (Senior)';
}

function getGradeKey(semester: string): string {
  const sem = parseInt(semester, 10);
  if (sem <= 2) return 'Freshman';
  if (sem <= 4) return 'Sophomore';
  if (sem <= 6) return 'Junior';
  return 'Senior';
}

function validateFile(file: File): { ok: boolean; error?: string } {
  const validExtensions = ['.pdf', '.docx', '.doc', '.txt', '.png', '.jpg', '.jpeg'];
  const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
  if (!validExtensions.includes(ext)) {
    return { ok: false, error: '不支持的文件类型。仅支持 PDF, DOCX, DOC, TXT, PNG, JPG, JPEG 格式' };
  }
  if (file.size > 20 * 1024 * 1024) {
    return { ok: false, error: '文件大小超出20MB上限' };
  }
  return { ok: true };
}

interface UploadZoneProps {
  onSuccess: () => void;
  onError: (error: string) => void;
}

export function UploadZone({ onSuccess, onError }: UploadZoneProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragActive, setIsDragActive] = useState(false);

  const processFile = (file: File) => {
    const check = validateFile(file);
    if (!check.ok) {
      onError(check.error || '文件验证失败');
    } else {
      onSuccess();
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setIsDragActive(true);
    } else if (e.type === 'dragleave') {
      setIsDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processFile(e.dataTransfer.files[0]);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      processFile(e.target.files[0]);
    }
  };

  const handleClick = () => {
    fileInputRef.current?.click();
  };

  return (
    <div
      className={`upload-zone ${isDragActive ? 'drag-active' : ''}`}
      onDragEnter={handleDrag}
      onDragOver={handleDrag}
      onDragLeave={handleDrag}
      onDrop={handleDrop}
      onClick={handleClick}
      data-testid="dropzone"
    >
      <input
        ref={fileInputRef}
        type="file"
        className="file-input-hidden"
        onChange={handleChange}
        accept=".pdf,.docx,.doc,.txt,.png,.jpg,.jpeg"
      />
      <div className="upload-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M12 16V8M12 8L9 11M12 8L15 11M20 16.5C20 18.98 17.98 21 15.5 21H8.5C6.02 21 4 18.98 4 16.5C4 14.37 5.48 12.59 7.47 12.11C8.01 7.55 11.89 4 16.5 4C18.43 4 20.14 4.62 21.5 5.67C23.16 6.94 24 9.17 24 11.5C24 13.9 22.38 15.96 20 16.5Z" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </div>
      <p className="upload-title">拖拽或点击上传培养方案文档</p>
      <p className="upload-hint">支持 PDF, DOCX, DOC, TXT, PNG, JPG, JPEG 格式，文件大小不超过 20MB</p>
    </div>
  );
}

interface BreathingLoaderProps {
  onFinished: () => void;
}

export function BreathingLoader({ onFinished }: BreathingLoaderProps) {
  useEffect(() => {
    const timer = setTimeout(() => {
      onFinished();
    }, 3000);
    return () => clearTimeout(timer);
  }, [onFinished]);

  return (
    <div className="loader-container">
      <div className="pulse-halo-container">
        <div className="pulse-halo breathing" />
      </div>
      <div className="loader-content">
        <h3 className="loader-title">正在读取培养方案并由AI对齐大纲...</h3>
        <p className="loader-subtitle">解析人培体系、智能提取核心知识节点，这需要几秒钟的宁静时刻</p>
      </div>
    </div>
  );
}

interface CourseRowProps {
  course: BranchCourseNode;
  isActive: boolean;
  onClick: () => void;
}

export function CourseRow({ course, isActive, onClick }: CourseRowProps) {
  const semesterText = `学期 ${course.time_arrangement?.semester_scope ?? '?'}`;
  const durationText = course.time_arrangement?.duration ?? '';

  return (
    <div
      className={`course-row ${isActive ? 'row-active' : ''}`}
      onClick={onClick}
    >
      <div className="course-info">
        <span className="course-semester">{semesterText}</span>
        <span className="course-theme">{course.course_or_chapter_theme}</span>
      </div>
      <div className="course-meta">
        <span className="course-duration">{durationText}</span>
        <span className="course-edit-badge">编辑</span>
      </div>
    </div>
  );
}

interface GradeSectionProps {
  gradeName: string;
  courses: BranchCourseNode[];
  activeCourseId: string | null;
  onSelectCourse: (id: string) => void;
}

export function GradeSection({
  gradeName,
  courses,
  activeCourseId,
  onSelectCourse,
}: GradeSectionProps) {
  const [isFolded, setIsFolded] = useState(false);

  return (
    <div className="grade-section">
      <button
        type="button"
        className="grade-header"
        onClick={() => setIsFolded(!isFolded)}
      >
        <span className="grade-title">{gradeName}</span>
        <span className="fold-icon">{isFolded ? '▲' : '▼'}</span>
      </button>
      {!isFolded && (
        <div className="grade-content">
          {courses.map((course) => (
            <CourseRow
              key={course.course_node_id}
              course={course}
              isActive={course.course_node_id === activeCourseId}
              onClick={() => onSelectCourse(course.course_node_id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface TreeTableProps {
  courses: BranchCourseNode[];
  activeCourseId: string | null;
  onSelectCourse: (id: string) => void;
}

export function TreeTable({ courses, activeCourseId, onSelectCourse }: TreeTableProps) {
  const grades = [
    { key: 'Freshman', name: '大一 (Freshman)' },
    { key: 'Sophomore', name: '大二 (Sophomore)' },
    { key: 'Junior', name: '大三 (Junior)' },
    { key: 'Senior', name: '大四 (Senior)' },
  ];

  return (
    <div className="tree-table">
      {grades.map((grade) => {
        const gradeCourses = courses.filter(
          (c) => getGradeKey(c.time_arrangement?.semester_scope ?? '1') === grade.key
        );
        return (
          <GradeSection
            key={grade.key}
            gradeName={grade.name}
            courses={gradeCourses}
            activeCourseId={activeCourseId}
            onSelectCourse={onSelectCourse}
          />
        );
      })}
    </div>
  );
}

interface FieldProps {
  course: BranchCourseNode;
  onChange: (key: string, value: unknown) => void;
}

export function GeneralFields({ course, onChange }: FieldProps) {
  return (
    <div className="form-section">
      <div className="form-group">
        <label htmlFor="course_theme">课程名称</label>
        <input
          id="course_theme"
          type="text"
          value={course.course_or_chapter_theme}
          onChange={(e) => onChange('course_or_chapter_theme', e.target.value)}
          placeholder="请输入课程名称"
          className="drawer-input"
        />
      </div>
      <div className="form-group">
        <label htmlFor="course_goal">课程目标</label>
        <textarea
          id="course_goal"
          value={course.course_goal}
          onChange={(e) => onChange('course_goal', e.target.value)}
          placeholder="请输入课程目标"
          className="drawer-textarea"
          rows={3}
        />
      </div>
    </div>
  );
}

export function TimeFields({ course, onChange }: FieldProps) {
  const time = course.time_arrangement;
  return (
    <div className="form-section">
      <h3 className="section-title">时间编排</h3>
      <div className="form-row">
        <div className="form-group half">
          <label htmlFor="semester_scope">建议学期</label>
          <select
            id="semester_scope"
            value={time?.semester_scope ?? '1'}
            onChange={(e) => onChange('semester_scope', e.target.value)}
            className="drawer-select"
          >
            {[1, 2, 3, 4, 5, 6, 7, 8].map((s) => (
              <option key={s} value={String(s)}>
                学期 {s}
              </option>
            ))}
          </select>
        </div>
        <div className="form-group half">
          <label htmlFor="duration">课程时长/学分</label>
          <input
            id="duration"
            type="text"
            value={time?.duration ?? ''}
            onChange={(e) => onChange('duration', e.target.value)}
            placeholder="如：64学时/4学分"
            className="drawer-input"
          />
        </div>
      </div>
      <div className="form-group">
        <label htmlFor="pace_reason">开课原因（可选）</label>
        <textarea
          id="pace_reason"
          value={time?.pace_reason ?? ''}
          onChange={(e) => onChange('pace_reason', e.target.value)}
          placeholder="例如：为后续数据结构奠定编程基础"
          className="drawer-textarea"
          rows={2}
        />
      </div>
    </div>
  );
}

export function PointFields({ course, onChange }: FieldProps) {
  const handleArrayChange = (key: 'key_points' | 'difficult_points' | 'acceptance_criteria', text: string) => {
    const arr = text.split('\n').map((s) => s.trim()).filter(Boolean);
    onChange(key, arr);
  };

  return (
    <div className="form-section">
      <h3 className="section-title">课程要点</h3>
      <div className="form-group">
        <label htmlFor="key_points">核心要点 (每行一个)</label>
        <textarea
          id="key_points"
          value={course.key_points?.join('\n') ?? ''}
          onChange={(e) => handleArrayChange('key_points', e.target.value)}
          placeholder="请输入核心要点，每行一个"
          className="drawer-textarea"
          rows={3}
        />
      </div>
      <div className="form-group">
        <label htmlFor="difficult_points">难点说明 (每行一个)</label>
        <textarea
          id="difficult_points"
          value={course.difficult_points?.join('\n') ?? ''}
          onChange={(e) => handleArrayChange('difficult_points', e.target.value)}
          placeholder="请输入难点说明，每行一个"
          className="drawer-textarea"
          rows={3}
        />
      </div>
      <div className="form-group">
        <label htmlFor="acceptance_criteria">验收标准 (每行一个)</label>
        <textarea
          id="acceptance_criteria"
          value={course.acceptance_criteria?.join('\n') ?? ''}
          onChange={(e) => handleArrayChange('acceptance_criteria', e.target.value)}
          placeholder="请输入验收标准，每行一个"
          className="drawer-textarea"
          rows={3}
        />
      </div>
    </div>
  );
}

interface DrawerFormProps {
  course: BranchCourseNode;
  onUpdateCourse: (updated: BranchCourseNode) => void;
}

export function DrawerForm({ course, onUpdateCourse }: DrawerFormProps) {
  const handleChange = (key: string, value: unknown) => {
    if (['semester_scope', 'duration', 'pace_reason'].includes(key)) {
      onUpdateCourse({
        ...course,
        time_arrangement: {
          semester_scope: course.time_arrangement?.semester_scope ?? '1',
          duration: course.time_arrangement?.duration ?? '',
          pace_reason: course.time_arrangement?.pace_reason,
          [key]: value as string,
        },
      });
    } else {
      onUpdateCourse({
        ...course,
        [key]: value,
      } as unknown as BranchCourseNode);
    }
  };

  return (
    <form className="drawer-form" onSubmit={(e) => e.preventDefault()}>
      <GeneralFields course={course} onChange={handleChange} />
      <TimeFields course={course} onChange={handleChange} />
      <PointFields course={course} onChange={handleChange} />
    </form>
  );
}

interface DetailDrawerProps {
  course: BranchCourseNode | null;
  onClose: () => void;
  onUpdateCourse: (updated: BranchCourseNode) => void;
}

export function DetailDrawer({ course, onClose, onUpdateCourse }: DetailDrawerProps) {
  const reduceMotion = useReducedMotion();
  if (!course) return null;

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <motion.div
        className="detail-drawer"
        onClick={(e) => e.stopPropagation()}
        initial={reduceMotion ? { opacity: 0 } : { x: '100%' }}
        animate={reduceMotion ? { opacity: 1 } : { x: 0 }}
        exit={reduceMotion ? { opacity: 0 } : { x: '100%' }}
        transition={reduceMotion ? { duration: 0.12 } : motionTokens.lazy}
      >
        <div className="drawer-header">
          <h2 className="drawer-title">编辑课程大纲</h2>
          <button type="button" className="drawer-close-btn" onClick={onClose}>
            ✕
          </button>
        </div>
        <div className="drawer-body">
          <DrawerForm course={course} onUpdateCourse={onUpdateCourse} />
        </div>
      </motion.div>
    </div>
  );
}

export function TeacherPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const reduceMotion = useReducedMotion();
  const [pageState, setPageState] = useState<TeacherPageState>('empty');
  const [courses, setCourses] = useState<BranchCourseNode[]>([]);
  const [activeCourseId, setActiveCourseId] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const [activeTab, setActiveTab] = useState<'editor' | 'graph'>('editor');
  const [isDropdownOpen, setIsDropdownOpen] = useState<boolean>(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const graphData = useMemo(() => {
    const nodeStatusMap: Record<string, string> = {};
    const nodes: GraphNode[] = courses.map((c) => {
      const status = c.course_node_id === activeCourseId
        ? 'in-progress'
        : (c.is_custom || (c.key_points && c.key_points.length > 0)
          ? 'completed'
          : 'locked');
      nodeStatusMap[c.course_node_id] = status;

      return {
        id: c.course_node_id,
        title: c.course_or_chapter_theme,
        status,
        agentMessage: `第 ${c.time_arrangement?.semester_scope ?? '?'} 学期`,
        completedConcepts: c.key_points?.length || 0,
        totalConcepts: (c.key_points?.length || 0) + (c.difficult_points?.length || 0) || 5,
      };
    });

    const edges: GraphEdge[] = [];
    courses.forEach((c) => {
      if (c.prerequisite_ids && c.prerequisite_ids.length > 0) {
        c.prerequisite_ids.forEach((pId) => {
          const sourceStatus = nodeStatusMap[pId];
          const targetStatus = nodeStatusMap[c.course_node_id];
          const edgeStatus = (sourceStatus === 'completed' && targetStatus === 'completed')
            ? 'completed'
            : 'future';

          edges.push({
            id: `${pId}-${c.course_node_id}`,
            source: pId,
            target: c.course_node_id,
            status: edgeStatus,
          });
        });
      }
    });

    return { nodes, edges };
  }, [courses, activeCourseId]);

  const handleCanvasClick = (event: React.MouseEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement;
    const nodeWrapper = target.closest('.node-wrapper');
    if (nodeWrapper) {
      const nodeId = nodeWrapper.getAttribute('data-node-id');
      if (nodeId) {
        setActiveCourseId(nodeId);
      }
    }
  };

  useEffect(() => {
    if (!isDropdownOpen) return;
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isDropdownOpen]);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  useEffect(() => {
    const saved = localStorage.getItem('teacher_cultivation_program');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setCourses(parsed);
          setPageState('editor');
        }
      } catch (e) {
        // ignore
      }
    }
  }, []);

  const handleUploadSuccess = () => {
    setPageState('loading');
  };

  const handleUploadError = (err: string) => {
    setFileError(err);
    setPageState('error');
  };

  const handleLoaderFinished = () => {
    setCourses(MOCK_TEACHER_COURSES);
    setPageState('editor');
  };

  const handleSave = () => {
    localStorage.setItem('teacher_cultivation_program', JSON.stringify(courses));
    setToastMessage('人培方案已成功发布并对齐！');
    setTimeout(() => {
      setToastMessage(null);
    }, 1500);
  };

  const handleReimport = () => {
    if (window.confirm('确定要重新导入培养方案吗？当前所有修改将被覆盖。')) {
      localStorage.removeItem('teacher_cultivation_program');
      setCourses([]);
      setActiveCourseId(null);
      setPageState('empty');
    }
  };

  const renderContent = () => {
    switch (pageState) {
      case 'loading':
        return <BreathingLoader onFinished={handleLoaderFinished} />;
      case 'error':
        return (
          <div className="error-panel">
            <div className="error-icon">✕</div>
            <h3 className="error-title">文件解析失败</h3>
            <p className="error-message">{fileError}</p>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => {
                setFileError(null);
                setPageState('empty');
              }}
            >
              重新上传
            </button>
          </div>
        );
      case 'editor':
        if (activeTab === 'graph') {
          return (
            <div className="graph-view-container">
              <div className="canvas-panel">
                <div className="canvas-header">
                  <h3>方案关系图谱</h3>
                  <p>培养方案中课程前置依赖与关系拓扑图</p>
                </div>
                <div className="canvas-wrapper" onClick={handleCanvasClick}>
                  <OrganicCanvas nodes={graphData.nodes} edges={graphData.edges} />
                </div>
              </div>
              <div className="stats-distribution-panel">
                <div className="distribution-card">
                  <h4>学时与学分分布</h4>
                  <div style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--text-caption)' }}>
                    等待学术直方图数据加载...
                  </div>
                </div>
                <div className="distribution-card">
                  <h4>要点与难点分布</h4>
                  <div style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--text-caption)' }}>
                    等待要点难点分布数据加载...
                  </div>
                </div>
              </div>
            </div>
          );
        }
        return (
          <div className="editor-layout">
            <div className="editor-header">
              <div className="header-info">
                <h2>培养方案大纲对齐</h2>
                <p>教师：{user?.username ?? '教师'} | 正在编辑已对齐的人培课程方案</p>
              </div>
              <div className="header-actions">
                <button type="button" className="btn btn-secondary" onClick={handleReimport}>
                  重新导入
                </button>
                <button type="button" className="btn btn-primary" onClick={handleSave}>
                  保存并发布
                </button>
              </div>
            </div>
            <div className="editor-main">
              <TreeTable
                courses={courses}
                activeCourseId={activeCourseId}
                onSelectCourse={setActiveCourseId}
              />
            </div>
          </div>
        );
      case 'empty':
      default:
        return <UploadZone onSuccess={handleUploadSuccess} onError={handleUploadError} />;
    }
  };

  return (
    <motion.main
      className="teacher-page teacher-page-with-header"
      initial={reduceMotion ? false : { opacity: 0, y: 16 }}
      animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
      transition={reduceMotion ? undefined : { duration: 0.76, ease: [0.25, 1, 0.5, 1] }}
    >
      <header className="teacher-header">
        <div className="teacher-brand">
          <img src="/logo.png" alt="one-tree logo" className="teacher-logo-img" />
          <span className="teacher-brand-name">one-tree 教师工作台</span>
        </div>
        <div className="teacher-nav-tabs">
          <button
            type="button"
            className={`teacher-tab ${activeTab === 'editor' ? 'tab-active' : ''} ${courses.length === 0 ? 'tab-disabled' : ''}`}
            disabled={courses.length === 0}
            onClick={() => {
              if (courses.length > 0) {
                setActiveTab('editor');
              }
            }}
          >
            大纲对齐编辑
            {activeTab === 'editor' && <div className="teacher-tab-indicator" />}
          </button>
          <button
            type="button"
            className={`teacher-tab ${activeTab === 'graph' ? 'tab-active' : ''} ${courses.length === 0 ? 'tab-disabled' : ''}`}
            disabled={courses.length === 0}
            onClick={() => {
              if (courses.length > 0) {
                setActiveTab('graph');
              }
            }}
          >
            方案关系图谱
            {activeTab === 'graph' && <div className="teacher-tab-indicator" />}
          </button>
        </div>
        <div className="teacher-user-area" ref={dropdownRef}>
          <button
            type="button"
            className="teacher-avatar-btn"
            onClick={() => setIsDropdownOpen(!isDropdownOpen)}
          >
            {user?.username ? user.username.substring(0, 1).toUpperCase() : '教'}
          </button>
          {isDropdownOpen && (
            <div className="teacher-user-dropdown">
              <div className="teacher-dropdown-header">
                <span className="teacher-dropdown-name">{user?.username ?? '教师'}</span>
                <span>{user?.identifier ?? 'teacher@example.com'}</span>
              </div>
              <button
                type="button"
                className="teacher-dropdown-item teacher-dropdown-item-logout"
                onClick={handleLogout}
              >
                <LogOut size={16} style={{ marginRight: 'var(--space-8)', display: 'inline-block', verticalAlign: 'middle' }} />
                <span style={{ verticalAlign: 'middle' }}>退出登录</span>
              </button>
            </div>
          )}
        </div>
      </header>

      <div className="teacher-container">
        {renderContent()}
      </div>
      <AnimatePresence>
        {activeCourseId && (
          <DetailDrawer
            key="drawer"
            course={courses.find((c) => c.course_node_id === activeCourseId) || null}
            onClose={() => setActiveCourseId(null)}
            onUpdateCourse={(updated) => {
              setCourses((prev) =>
                prev.map((c) => (c.course_node_id === updated.course_node_id ? updated : c))
              );
            }}
          />
        )}
      </AnimatePresence>
      <AnimatePresence>
        {toastMessage && (
          <motion.div
            key="toast"
            className="toast-message"
            initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 20 }}
            animate={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
            exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 20 }}
            transition={reduceMotion ? { duration: 0.12 } : motionTokens.lazy}
          >
            {toastMessage}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.main>
  );
}
