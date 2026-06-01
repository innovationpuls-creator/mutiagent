import styled from 'styled-components';
import type { LearningPathResult } from '../../types/chat';

interface LearningPathCardProps {
  path: LearningPathResult;
}

interface ListBlockProps {
  items: string[];
}

function ListBlock({ items }: ListBlockProps) {
  if (items.length === 0) {
    return <EmptyText>等待进一步补充。</EmptyText>;
  }

  return (
    <List>
      {items.map((item, index) => (
        <li key={`${item}-${index}`}>{item}</li>
      ))}
    </List>
  );
}

function TextPair({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value || '等待进一步补充。'}</dd>
    </div>
  );
}

export function LearningPathCard({ path }: LearningPathCardProps) {
  return (
    <Card>
      <Header>
        <span>学习路径</span>
        <strong>为你整理的学习路径</strong>
      </Header>

      <Section>
        <h3>明确学习目标</h3>
        <GoalGrid>
          <TextPair label="目标课程或技能" value={path.learning_goal.target_course_or_skill} />
          <TextPair label="目标完成时间" value={path.learning_goal.target_completion_time} />
          <TextPair label="学习目标类型" value={path.learning_goal.goal_type} />
          <TextPair label="最终效果" value={path.learning_goal.desired_outcome} />
        </GoalGrid>
      </Section>

      <Section>
        <h3>分析当前差距</h3>
        <SubSection>
          <h4>当前已掌握内容</h4>
          <ListBlock items={path.gap_analysis.current_mastered_content} />
        </SubSection>
        <SubSection>
          <h4>当前薄弱环节</h4>
          <ListBlock items={path.gap_analysis.current_weaknesses} />
        </SubSection>
        <SubSection>
          <h4>目标所需能力</h4>
          <ListBlock items={path.gap_analysis.required_capabilities} />
        </SubSection>
        <SubSection>
          <h4>主要差距</h4>
          <ListBlock items={path.gap_analysis.main_gaps} />
        </SubSection>
      </Section>

      <Section>
        <h3>规划基础学习路径</h3>
        <StageStack>
          {path.foundation_path.stages.map((stage) => (
            <StageCard key={stage.stage_id}>
              <StageHeader>
                <span>{stage.stage_id}</span>
                <h4>{stage.stage_name}</h4>
              </StageHeader>
              <p>{stage.learning_goal}</p>
              <StageGrid>
                <SubSection>
                  <h5>学习内容</h5>
                  <ListBlock items={stage.learning_content} />
                </SubSection>
                <SubSection>
                  <h5>学习任务</h5>
                  <ListBlock items={stage.learning_tasks} />
                </SubSection>
                <SubSection>
                  <h5>推荐方法</h5>
                  <ListBlock items={stage.recommended_methods} />
                </SubSection>
                <SubSection>
                  <h5>完成标准</h5>
                  <ListBlock items={stage.completion_standard} />
                </SubSection>
              </StageGrid>
            </StageCard>
          ))}
        </StageStack>
      </Section>

      <Section>
        <h3>生成学习路径</h3>
        <Overview>{path.generated_path.overall_goal}</Overview>
        <RouteGrid>
          <SubSection>
            <h4>阶段路线</h4>
            <ListBlock
              items={path.generated_path.stage_routes.map((route) => `${route.stage_id}：${route.route_summary}`)}
            />
          </SubSection>
          <SubSection>
            <h4>学习节奏</h4>
            <ListBlock
              items={path.generated_path.schedule.map(
                (item) => `${item.period}：${item.focus}，${item.milestone}`,
              )}
            />
          </SubSection>
          <SubSection>
            <h4>任务清单</h4>
            <ListBlock items={path.generated_path.task_checklist} />
          </SubSection>
          <SubSection>
            <h4>资源类型</h4>
            <ListBlock items={path.generated_path.recommended_resource_types} />
          </SubSection>
          <SubSection>
            <h4>验收标准</h4>
            <ListBlock
              items={path.generated_path.stage_acceptance_criteria.flatMap((item) =>
                item.criteria.map((criterion) => `${item.stage_id}：${criterion}`),
              )}
            />
          </SubSection>
          <SubSection>
            <h4>下一步行动</h4>
            <ListBlock items={path.generated_path.next_actions} />
          </SubSection>
        </RouteGrid>
      </Section>
    </Card>
  );
}

const Card = styled.article`
  inline-size: min(100%, var(--container-default));
  display: grid;
  gap: var(--space-24);
  align-self: flex-start;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background:
    radial-gradient(circle at 12% 0%, oklch(84% 0.12 63 / 0.18), transparent 30%),
    var(--color-surface-raised);
  box-shadow: var(--shadow-md);
  padding: var(--space-24);
  color: var(--color-text-primary);
  font-family: var(--font-body);

  h3,
  h4,
  h5,
  p,
  dl,
  dd {
    margin: 0;
  }

  h3 {
    color: var(--color-text-primary);
    font-size: var(--text-h5);
    font-weight: var(--font-weight-medium);
    line-height: 1.4;
  }

  h4,
  h5,
  dt {
    color: var(--color-text-secondary);
    font-size: var(--text-body-sm);
    font-weight: var(--font-weight-medium);
    line-height: 1.6;
  }

  p,
  dd,
  li {
    color: var(--color-text-primary);
    font-size: var(--text-body-sm);
    line-height: 1.8;
    text-wrap: pretty;
  }

  @media (max-width: 767px) {
    padding: var(--space-24);
  }
`;

const Header = styled.header`
  display: grid;
  gap: var(--space-4);
  border-radius: var(--radius-md);
  background: var(--color-primary-soft);
  padding: var(--space-16) var(--space-24);

  span {
    color: var(--color-text-secondary);
    font-size: var(--text-caption);
    line-height: 1.6;
  }

  strong {
    color: var(--color-text-primary);
    font-size: var(--text-h4);
    font-weight: var(--font-weight-medium);
    line-height: 1.4;
    text-wrap: pretty;
  }
`;

const Section = styled.section`
  display: grid;
  gap: var(--space-16);
`;

const SubSection = styled.div`
  display: grid;
  gap: var(--space-8);
  min-inline-size: 0;
`;

const GoalGrid = styled.dl`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(var(--container-narrow), 100%), 1fr));
  gap: var(--space-12);

  div {
    display: grid;
    gap: var(--space-4);
    border-radius: var(--radius-md);
    background: var(--color-surface);
    padding: var(--space-12) var(--space-16);
  }
`;

const List = styled.ul`
  display: grid;
  gap: var(--space-4);
  margin: 0;
  padding-inline-start: var(--space-24);

  li::marker {
    color: var(--color-primary);
  }
`;

const EmptyText = styled.p`
  color: var(--color-text-muted);
`;

const StageStack = styled.div`
  display: grid;
  gap: var(--space-16);
`;

const StageCard = styled.article`
  display: grid;
  gap: var(--space-12);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  box-shadow: var(--shadow-sm);
  padding: var(--space-16);
`;

const StageHeader = styled.header`
  display: flex;
  align-items: center;
  gap: var(--space-12);

  span {
    border-radius: var(--radius-full);
    background: var(--color-secondary-soft);
    color: var(--color-text-secondary);
    font-size: var(--text-caption);
    line-height: 1.6;
    padding: var(--space-4) var(--space-8);
  }
`;

const StageGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(var(--container-narrow), 100%), 1fr));
  gap: var(--space-16);
`;

const Overview = styled.p`
  border-radius: var(--radius-md);
  background: var(--color-surface-inset);
  padding: var(--space-12) var(--space-16);
`;

const RouteGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(var(--container-narrow), 100%), 1fr));
  gap: var(--space-16);
`;
