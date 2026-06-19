import { useEffect, useMemo, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { Database, Trash2 } from 'lucide-react';
import { motion, useReducedMotion } from 'framer-motion';
import { adminApi as defaultAdminApi, type AdminAccountApi } from '../../api/admin';
import { adminDataApi as defaultAdminDataApi, type DataCohort, type DataOverview, type UserLearningData } from '../../api/adminData';
import type { CultivationProgram } from '../../api/teacherProgram';
import { useAuth } from '../../contexts/AuthContext';
import type { AuthUser } from '../../types/auth';
import './admin.css';

type DataTab = 'overview' | 'cohorts' | 'programs' | 'learning' | 'sessions';

interface AdminDataPageProps {
  adminApi?: AdminAccountApi;
  adminDataApi?: typeof defaultAdminDataApi;
}

const adminRoutes = [
  { label: '账号管理', path: '/admin/accounts', hint: '用户账号管理' },
  { label: '人培方案', path: '/admin/programs', hint: '上传与发布人培方案' },
  { label: '数据管理', path: '/admin/data', hint: '学习数据与人培方案管理' },
];

const tabs: { value: DataTab; label: string }[] = [
  { value: 'overview', label: '概览' },
  { value: 'cohorts', label: '组织班级' },
  { value: 'programs', label: '人培方案' },
  { value: 'learning', label: '学习数据' },
  { value: 'sessions', label: '会话数据' },
];

function matchesCohortText(text: string, school: string, major: string, className: string) {
  if (!text) return true;
  return school.includes(text) || major.includes(text) || className.includes(text);
}

function dataCount(data: UserLearningData | null, key: keyof Omit<UserLearningData, 'user' | 'profile'>) {
  return data?.[key].length ?? 0;
}

export function AdminDataPage({ adminApi = defaultAdminApi, adminDataApi = defaultAdminDataApi }: AdminDataPageProps) {
  const { token, user } = useAuth();
  const reduceMotion = useReducedMotion();
  const [activeTab, setActiveTab] = useState<DataTab>('overview');
  const [overview, setOverview] = useState<DataOverview | null>(null);
  const [cohorts, setCohorts] = useState<DataCohort[]>([]);
  const [programs, setPrograms] = useState<CultivationProgram[]>([]);
  const [accounts, setAccounts] = useState<AuthUser[]>([]);
  const [selectedUid, setSelectedUid] = useState('');
  const [learningData, setLearningData] = useState<UserLearningData | null>(null);
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const [nextOverview, nextCohorts, nextPrograms, nextAccounts] = await Promise.all([
        adminDataApi.overview(token),
        adminDataApi.cohorts(token),
        adminDataApi.programs(token),
        adminApi.listAccounts(token),
      ]);
      setOverview(nextOverview);
      setCohorts(nextCohorts);
      setPrograms(nextPrograms);
      setAccounts(nextAccounts);
      setSelectedUid((current) => current || nextAccounts[0]?.uid || '');
    } catch (dataError) {
      setError(dataError instanceof Error ? dataError.message : '数据管理加载失败');
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, [token]);

  useEffect(() => {
    if (!token || !selectedUid) {
      setLearningData(null);
      return;
    }
    let cancelled = false;
    adminDataApi.userLearningData(token, selectedUid)
      .then((data) => {
        if (!cancelled) setLearningData(data);
      })
      .catch((dataError) => {
        if (!cancelled) setError(dataError instanceof Error ? dataError.message : '学习数据加载失败');
      });
    return () => {
      cancelled = true;
    };
  }, [adminDataApi, selectedUid, token]);

  const filteredCohorts = useMemo(() => {
    const text = query.trim();
    return cohorts.filter((cohort) => matchesCohortText(text, cohort.school, cohort.major, cohort.class_name));
  }, [cohorts, query]);

  const filteredPrograms = useMemo(() => {
    const text = query.trim();
    return programs.filter((program) => (
      matchesCohortText(text, program.school, program.major, program.class_name) ||
      program.teacher_name.includes(text)
    ));
  }, [programs, query]);

  const selectedAccount = accounts.find((account) => account.uid === selectedUid) ?? null;

  const deleteSelectedLearningData = async () => {
    if (!token || !selectedUid) return;
    setBusy(true);
    setError(null);
    try {
      await adminDataApi.deleteUserLearningData(token, selectedUid);
      await loadData();
      setLearningData(null);
    } catch (dataError) {
      setError(dataError instanceof Error ? dataError.message : '学习数据清理失败');
    } finally {
      setBusy(false);
    }
  };

  const deleteProgram = async (cohort: DataCohort) => {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await adminDataApi.deleteCohortProgram(token, cohort);
      await loadData();
    } catch (dataError) {
      setError(dataError instanceof Error ? dataError.message : '人培方案删除失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <motion.main
      className="admin-page"
      initial={reduceMotion ? false : { opacity: 0, y: 16 }}
      animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
      transition={reduceMotion ? undefined : { duration: 0.76, ease: [0.25, 1, 0.5, 1] }}
    >
      <div className="admin-ambient-sun" aria-hidden="true" />
      <div className="admin-paper-canvas" aria-hidden="true" />
      <section className="admin-shell" aria-labelledby="admin-data-title">
        <nav className="admin-menu" aria-label="管理员菜单">
          <NavLink className="admin-logo-area" to="/admin/accounts" aria-label="回到后台首页">
            <span className="admin-logo-pebble" aria-hidden="true">
              <img src="/logo.png" alt="" className="admin-logo-img" />
            </span>
            <span className="admin-logo-brand">one-tree</span>
          </NavLink>
          <span className="admin-menu-links">
            {adminRoutes.map((route) => (
              <NavLink
                key={route.path}
                to={route.path}
                className={({ isActive }) => `admin-menu-link ${isActive ? 'active' : ''}`}
                title={route.hint}
              >
                {route.label}
              </NavLink>
            ))}
          </span>
          <span className="admin-user-chip">{user?.username ?? '管理员'}</span>
        </nav>

        <header className="admin-header">
          <div>
            <p className="admin-kicker">// data</p>
            <h1 id="admin-data-title">数据管理</h1>
          </div>
          <div className="admin-header-actions">
            <button className="admin-secondary-action" type="button" onClick={() => void loadData()} disabled={busy}>
              <Database aria-hidden="true" />
              <span>刷新数据</span>
            </button>
          </div>
        </header>

        <section className="admin-data-tabs" aria-label="数据管理分类">
          {tabs.map((tab) => (
            <button
              key={tab.value}
              type="button"
              className={`admin-data-tab ${activeTab === tab.value ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.value)}
            >
              {tab.label}
            </button>
          ))}
        </section>

        {activeTab !== 'overview' ? (
          <label className="admin-data-search">
            <span>筛选</span>
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="输入学校、专业、班级或教师" />
          </label>
        ) : null}

        {error ? <p className="admin-error">{error}</p> : null}

        {activeTab === 'overview' ? <OverviewPanel overview={overview} /> : null}
        {activeTab === 'cohorts' ? <CohortPanel cohorts={filteredCohorts} busy={busy} onDeleteProgram={deleteProgram} /> : null}
        {activeTab === 'programs' ? <ProgramPanel programs={filteredPrograms} /> : null}
        {activeTab === 'learning' || activeTab === 'sessions' ? (
          <LearningDataPanel
            accounts={accounts}
            selectedUid={selectedUid}
            selectedAccount={selectedAccount}
            learningData={learningData}
            mode={activeTab}
            busy={busy}
            onSelect={setSelectedUid}
            onDelete={() => void deleteSelectedLearningData()}
          />
        ) : null}
      </section>
    </motion.main>
  );
}

function OverviewPanel({ overview }: { overview: DataOverview | null }) {
  const learningCount = overview ? Object.values(overview.learning_data).reduce((total, value) => total + value, 0) : 0;
  return (
    <section className="admin-data-overview" aria-label="数据概览">
      <article><span>账号</span><strong>{overview ? Object.values(overview.accounts).reduce((total, value) => total + value, 0) : 0}</strong></article>
      <article><span>组织班级</span><strong>{overview?.cohorts ?? 0}</strong></article>
      <article><span>人培方案</span><strong>{overview?.programs ?? 0}</strong></article>
      <article><span>学习数据</span><strong>{learningCount}</strong></article>
    </section>
  );
}

function CohortPanel({
  cohorts,
  busy,
  onDeleteProgram,
}: {
  cohorts: DataCohort[];
  busy: boolean;
  onDeleteProgram(cohort: DataCohort): void;
}) {
  return (
    <section className="admin-data-table" aria-label="组织班级列表">
      <div className="admin-data-row admin-data-head">
        <span>学校</span><span>专业</span><span>班级</span><span>学生</span><span>管理员</span><span>方案</span><span>操作</span>
      </div>
      {cohorts.map((cohort) => (
        <div className="admin-data-row" key={`${cohort.school}-${cohort.major}-${cohort.class_name}`}>
          <span>{cohort.school}</span>
          <span>{cohort.major}</span>
          <span>{cohort.class_name}</span>
          <span>{cohort.student_count}</span>
          <span>{cohort.teacher_count}</span>
          <span>{cohort.has_program ? cohort.program_teacher_name ?? '已发布' : '暂无'}</span>
          <button type="button" disabled={busy || !cohort.has_program} onClick={() => onDeleteProgram(cohort)}>
            删除方案
          </button>
        </div>
      ))}
    </section>
  );
}

function ProgramPanel({ programs }: { programs: CultivationProgram[] }) {
  return (
    <section className="admin-data-table" aria-label="人培方案列表">
      <div className="admin-data-row admin-data-head">
        <span>学校</span><span>专业</span><span>班级</span><span>发布人</span><span>课程数</span><span>发布时间</span>
      </div>
      {programs.map((program) => (
        <div className="admin-data-row" key={program.program_id}>
          <span>{program.school}</span>
          <span>{program.major}</span>
          <span>{program.class_name}</span>
          <span>{program.teacher_name}</span>
          <span>{program.courses.length}</span>
          <span>{program.published_at ? new Date(program.published_at).toLocaleString('zh-CN') : '未发布'}</span>
        </div>
      ))}
    </section>
  );
}

function LearningDataPanel({
  accounts,
  selectedUid,
  selectedAccount,
  learningData,
  mode,
  busy,
  onSelect,
  onDelete,
}: {
  accounts: AuthUser[];
  selectedUid: string;
  selectedAccount: AuthUser | null;
  learningData: UserLearningData | null;
  mode: 'learning' | 'sessions';
  busy: boolean;
  onSelect(uid: string): void;
  onDelete(): void;
}) {
  return (
    <section className="admin-data-detail" aria-label={mode === 'learning' ? '学习数据详情' : '会话数据详情'}>
      <label>
        <span>账号</span>
        <select value={selectedUid} onChange={(event) => onSelect(event.target.value)}>
          {accounts.map((account) => (
            <option key={account.uid} value={account.uid}>
              {account.username} / {account.identifier}
            </option>
          ))}
        </select>
      </label>
      {selectedAccount ? (
        <div className="admin-data-user-card">
          <strong>{selectedAccount.username}</strong>
          <span>{selectedAccount.school} / {selectedAccount.major} / {selectedAccount.class_name}</span>
        </div>
      ) : null}
      {mode === 'learning' ? (
        <div className="admin-data-metrics">
          <article><span>画像</span><strong>{learningData?.profile ? 1 : 0}</strong></article>
          <article><span>学习路径</span><strong>{dataCount(learningData, 'year_learning_paths')}</strong></article>
          <article><span>课程大纲</span><strong>{dataCount(learningData, 'course_outlines')}</strong></article>
          <article><span>测验</span><strong>{dataCount(learningData, 'chapter_quizzes')}</strong></article>
          <article><span>进度</span><strong>{dataCount(learningData, 'chapter_progress')}</strong></article>
          <article><span>资源质量</span><strong>{dataCount(learningData, 'resource_quality')}</strong></article>
        </div>
      ) : (
        <div className="admin-data-metrics">
          <article><span>会话</span><strong>{dataCount(learningData, 'conversation_sessions')}</strong></article>
        </div>
      )}
      <button className="admin-danger-action" type="button" onClick={onDelete} disabled={busy || !selectedUid}>
        <Trash2 aria-hidden="true" />
        <span>清理该账号学习数据</span>
      </button>
    </section>
  );
}
