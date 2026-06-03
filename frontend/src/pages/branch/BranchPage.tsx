import { useState } from 'react';
import '../../components/home/BlankPage.css';
import './branch.css';
import { AnimatePresence, motion } from 'framer-motion';
import { motionTokens } from '../../styles/motion-tokens';
import { SegmentedControl } from '../../components/ui/SegmentedControl';
import { FreshmanView } from './views/FreshmanView';
import { SophomoreView } from './views/SophomoreView';
import { JuniorView } from './views/JuniorView';
import { SeniorView } from './views/SeniorView';

const YEARS = ['大一', '大二', '大三', '大四'];

export function BranchPage() {
  const [activeYear, setActiveYear] = useState(YEARS[0]);

  const renderView = () => {
    switch (activeYear) {
      case '大一': return <FreshmanView />;
      case '大二': return <SophomoreView />;
      case '大三': return <JuniorView />;
      case '大四': return <SeniorView />;
      default: return null;
    }
  };

  return (
    <motion.main className="home-page">
      {/* 继承自 BlankPage 的环境光和纸张底纹 */}
      <div className="home-ambient-sun" aria-hidden="true" />
      <div className="home-paper-canvas" aria-hidden="true" />

      <div className="home-content branch-content">
        {/* 顶部居中滑块 */}
        <nav className="branch-nav">
          <SegmentedControl 
            options={YEARS} 
            active={activeYear} 
            onChange={setActiveYear} 
          />
        </nav>

        {/* 内容展示区 */}
        <div className="branch-view-container">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeYear}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -16 }}
              transition={motionTokens.editorial}
              style={{ width: '100%' }}
            >
              {renderView()}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </motion.main>
  );
}
