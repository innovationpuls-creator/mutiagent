import type { ProfileDashboardData } from '../types/profile';

/**
 * Mock 用户画像数据
 * 基于用户提供的 Dify Agent 生成阶段 JSON 真实数据构建
 */
export const MOCK_PROFILE_DASHBOARD: ProfileDashboardData = {
  profile: {
    currentGrade: '大二',
    major: '软件工程',
    learningStage: '课程学习与项目实践并行',
    hasClearGoal: '有一定方向，但需要进一步细化',
    learningMethodPreference: '偏好案例驱动和实践驱动学习',
    learningPacePreference: '适合分阶段推进，每次完成一个小目标',
    contentPreference: ['视频', '文档', '练习题', '代码实践', '项目案例'],
    needGuidance: '需要较强引导和阶段性反馈',
    knowledgeFoundation: '具备一定编程基础和软件工程课程基础',
    strengths: '项目理解、需求拆解、页面设计表达',
    weaknesses: '系统化知识梳理、长期学习节奏、部分底层原理',
    experience: '有课程实验、项目原型和智能体相关实践经验',
    shortTermGoal: '完善课程学习和项目实践能力',
    longTermGoal: '提升软件开发与 AI 应用项目能力',
    weeklyAvailableTime: '每周约 6-10 小时',
    constraints: '时间较分散，目标容易变化，需要更清晰的学习路径',
  },

  profileCompleteness: 85,

  profileSummaryText:
    '你擅长项目理解与需求拆解，有不错的设计表达能力。' +
    '当前阶段适合通过案例驱动的方式，' +
    '在实践中补强系统化知识梳理和底层原理。',

  todayLearning: {
    title: '设计模式入门：从案例到代码',
    description:
      '结合你的项目经验，用真实场景理解 5 个最常用的设计模式。' +
      '每个模式配有可运行的代码示例，适合你偏好的实践驱动学习方式。',
    source: 'AI 个性化推荐',
    currentLearningCourse: null,
    currentCourseDetail: null,
    currentCourseOutline: null,
    gradeCourses: [],
    followingCourses: [],
  },

  recommendations: [
    {
      id: 'rec-1',
      title: '数据结构可视化',
      duration: '25 min',
      description: '巩固你的编程基础',
      accent: 'lavender',
    },
    {
      id: 'rec-2',
      title: '需求分析实战',
      duration: '15 min',
      description: '发挥你的拆解优势',
      accent: 'sage',
    },
    {
      id: 'rec-3',
      title: 'Git 工作流精要',
      duration: '10 min',
      description: '提升协作效率',
      accent: 'peach',
    },
  ],
};
