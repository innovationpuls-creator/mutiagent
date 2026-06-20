import styled from "styled-components";
import type {
	GradeId,
	LearningPathResult,
	ResourceDirection,
} from "../../types/chat";

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
			<dd>{value || "等待进一步补充。"}</dd>
		</div>
	);
}

const gradeOrder: GradeId[] = ["year_1", "year_2", "year_3", "year_4"];

const relationTypeLabels: Record<string, string> = {
	prerequisite: "先修",
	contains: "包含",
	parallel: "并行",
	reinforces: "强化",
	applies_to: "应用",
	extends: "扩展",
	review_before: "复习先于",
	resource_basis_for: "资源基础",
};

function findResourceDirections(
	path: LearningPathResult,
	ids: string[],
): ResourceDirection[] {
	return path.resource_generation_contract.resource_directions.filter(
		(direction) => ids.includes(direction.resource_direction_id),
	);
}

function buildPathTitle(
	gradePlans: NonNullable<LearningPathResult["grade_plans"][GradeId]>[],
	currentLearningCourse?: LearningPathResult["current_learning_course"],
): string {
	if (currentLearningCourse?.grade_id) {
		const activePlan = gradePlans.find(
			(p) => p.grade_id === currentLearningCourse.grade_id,
		);
		if (activePlan) {
			return `${activePlan.grade_name}课程路径`;
		}
	}
	if (gradePlans.length === 1) {
		return `${gradePlans[0].grade_name}课程路径`;
	}
	if (gradePlans.length > 1) {
		return "多学年课程路径";
	}
	return "当前年级课程路径";
}

export function LearningPathCard({ path }: LearningPathCardProps) {
	const orderedGradePlans = gradeOrder
		.map((gradeId) => path.grade_plans[gradeId])
		.filter((gradePlan) => gradePlan !== undefined);
	const pathTitle = buildPathTitle(
		orderedGradePlans,
		path.current_learning_course,
	);

	return (
		<Card>
			<Header>
				<span>学习路径 · {path.schema_version}</span>
				<strong>{pathTitle}</strong>
			</Header>

			<Section>
				<h3>目标与基础画像</h3>
				<GoalGrid>
					<TextPair
						label="目标课程或技能"
						value={path.learning_goal.target_course_or_skill}
					/>
					<TextPair label="学习目标类型" value={path.learning_goal.goal_type} />
					<TextPair
						label="最终效果"
						value={path.learning_goal.desired_outcome}
					/>
					<TextPair
						label="四年结果"
						value={path.learning_goal.four_year_outcome}
					/>
					<TextPair
						label="当前年级"
						value={path.learner_baseline.current_grade}
					/>
					<TextPair label="专业方向" value={path.learner_baseline.major} />
					<TextPair
						label="每周可用时间"
						value={path.learner_baseline.weekly_available_time}
					/>
				</GoalGrid>
			</Section>

			<Section>
				<h3>画像约束</h3>
				<RouteGrid>
					<SubSection>
						<h4>已掌握内容</h4>
						<ListBlock items={path.learner_baseline.mastered_content} />
					</SubSection>
					<SubSection>
						<h4>薄弱环节</h4>
						<ListBlock items={path.learner_baseline.weaknesses} />
					</SubSection>
					<SubSection>
						<h4>学习约束</h4>
						<ListBlock items={path.learner_baseline.constraints} />
					</SubSection>
				</RouteGrid>
			</Section>

			<Section>
				<h3>年级课程节点</h3>
				<GradeStack>
					{orderedGradePlans.map((gradePlan) => (
						<GradeCard key={gradePlan.grade_id}>
							<GradeHeader>
								<span>{gradePlan.grade_id}</span>
								<div>
									<h4>{gradePlan.grade_name}</h4>
									<p>{gradePlan.grade_goal}</p>
								</div>
							</GradeHeader>

							<CourseStack>
								{gradePlan.course_nodes.map((courseNode) => (
									<CourseCard key={courseNode.course_node_id}>
										<CourseHeader>
											<div>
												<span>{courseNode.course_node_id}</span>
												<h5>{courseNode.course_or_chapter_theme}</h5>
											</div>
											<TimePill>
												{courseNode.time_arrangement.semester_scope} ·{" "}
												{courseNode.time_arrangement.duration}
											</TimePill>
										</CourseHeader>

										<Overview>{courseNode.course_goal}</Overview>

										<StageGrid>
											<SubSection>
												<h5>先修知识</h5>
												<ListBlock items={courseNode.prerequisite_node_ids} />
											</SubSection>
											<SubSection>
												<h5>学习顺序</h5>
												<ListBlock items={courseNode.learning_sequence} />
											</SubSection>
											<SubSection>
												<h5>重点</h5>
												<ListBlock items={courseNode.key_points} />
											</SubSection>
											<SubSection>
												<h5>难点</h5>
												<ListBlock items={courseNode.difficult_points} />
											</SubSection>
										</StageGrid>

										<SubSection>
											<h5>核心知识点</h5>
											<KnowledgeGrid>
												{courseNode.core_knowledge_points.map(
													(knowledgePoint) => (
														<KnowledgeItem
															key={knowledgePoint.knowledge_point_id}
														>
															<span>{knowledgePoint.level}</span>
															<strong>{knowledgePoint.name}</strong>
															<p>{knowledgePoint.description}</p>
															<small>{knowledgePoint.mastery_standard}</small>
														</KnowledgeItem>
													),
												)}
											</KnowledgeGrid>
										</SubSection>

										<SubSection>
											<h5>章节与知识点层级</h5>
											<ChapterStack>
												{courseNode.chapter_nodes.map((chapterNode) => (
													<ChapterCard key={chapterNode.chapter_node_id}>
														<strong>{chapterNode.chapter_theme}</strong>
														<ListBlock
															items={chapterNode.knowledge_hierarchy.map(
																(item) =>
																	`${item.hierarchy_level}：${item.title}，${item.summary}`,
															)}
														/>
													</ChapterCard>
												))}
											</ChapterStack>
										</SubSection>

										<SubSection>
											<h5>知识点之间的关系</h5>
											<ListBlock
												items={courseNode.knowledge_relations.map(
													(relation) =>
														`${relation.from_node_id} ${relationTypeLabels[relation.relation_type]} ${relation.to_node_id}：${relation.description}`,
												)}
											/>
										</SubSection>

										<SubSection>
											<h5>后续资源生成方向</h5>
											<ResourceGrid>
												{findResourceDirections(
													path,
													courseNode.downstream_resource_direction_ids,
												).map((direction) => (
													<ResourceItem key={direction.resource_direction_id}>
														<span>
															{direction.resource_type} ·{" "}
															{direction.difficulty_level}
														</span>
														<strong>{direction.generation_goal}</strong>
														<ListBlock items={direction.content_requirements} />
													</ResourceItem>
												))}
											</ResourceGrid>
										</SubSection>

										<SubSection>
											<h5>验收标准</h5>
											<ListBlock items={courseNode.acceptance_criteria} />
										</SubSection>
									</CourseCard>
								))}
							</CourseStack>
						</GradeCard>
					))}
				</GradeStack>
			</Section>

			<Section>
				<h3>全局关系与更新规则</h3>
				<RouteGrid>
					<SubSection>
						<h4>关键路径</h4>
						<ListBlock
							items={path.knowledge_graph.critical_paths.map(
								(pathItem) =>
									`${pathItem.purpose}：${pathItem.ordered_node_ids.join(" → ")}`,
							)}
						/>
					</SubSection>
					<SubSection>
						<h4>跨节点关系</h4>
						<ListBlock
							items={path.knowledge_graph.global_relations.map(
								(relation) =>
									`${relation.from_node_id} ${relationTypeLabels[relation.relation_type]} ${relation.to_node_id}：${relation.description}`,
							)}
						/>
					</SubSection>
					<SubSection>
						<h4>后续资源生成方向</h4>
						<ListBlock
							items={path.resource_generation_contract.resource_directions.map(
								(direction) =>
									`${direction.resource_type}：${direction.generation_goal}`,
							)}
						/>
					</SubSection>
					<SubSection>
						<h4>动态更新依据</h4>
						<ListBlock
							items={[
								...path.dynamic_update_contract.trackable_metrics,
								...path.dynamic_update_contract.update_triggers,
							]}
						/>
					</SubSection>
					<SubSection>
						<h4>调整策略</h4>
						<Overview>
							{path.dynamic_update_contract.adjustment_strategy}
						</Overview>
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

const GradeStack = styled.div`
  display: grid;
  gap: var(--space-16);
`;

const GradeCard = styled.article`
  display: grid;
  gap: var(--space-16);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  box-shadow: var(--shadow-sm);
  padding: var(--space-16);
`;

const GradeHeader = styled.header`
  display: flex;
  align-items: flex-start;
  gap: var(--space-12);

  span {
    flex: 0 0 auto;
    border-radius: var(--radius-full);
    background: var(--color-secondary-soft);
    color: var(--color-text-secondary);
    font-size: var(--text-caption);
    line-height: 1.6;
    padding: var(--space-4) var(--space-8);
  }

  div {
    display: grid;
    gap: var(--space-4);
    min-inline-size: 0;
  }
`;

const CourseStack = styled.div`
  display: grid;
  gap: var(--space-12);
`;

const CourseCard = styled.article`
  display: grid;
  gap: var(--space-16);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-raised);
  padding: var(--space-16);
`;

const CourseHeader = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-12);

  div {
    display: grid;
    gap: var(--space-4);
    min-inline-size: 0;
  }

  span {
    color: var(--color-text-muted);
    font-size: var(--text-caption);
    line-height: 1.6;
  }

  @media (max-width: 767px) {
    display: grid;
  }
`;

const TimePill = styled.p`
  flex: 0 0 auto;
  border-radius: var(--radius-full);
  background: var(--color-primary-soft);
  color: var(--color-text-secondary);
  font-size: var(--text-caption);
  line-height: 1.6;
  padding: var(--space-4) var(--space-12);
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

const KnowledgeGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(var(--container-narrow), 100%), 1fr));
  gap: var(--space-12);
`;

const KnowledgeItem = styled.article`
  display: grid;
  gap: var(--space-4);
  border-radius: var(--radius-md);
  background: var(--color-secondary-soft);
  padding: var(--space-12) var(--space-16);

  span,
  small {
    color: var(--color-text-secondary);
    font-size: var(--text-caption);
    line-height: 1.6;
  }

  strong {
    color: var(--color-text-primary);
    font-size: var(--text-body-sm);
    font-weight: var(--font-weight-medium);
    line-height: 1.6;
  }
`;

const ChapterStack = styled.div`
  display: grid;
  gap: var(--space-8);
`;

const ChapterCard = styled.article`
  display: grid;
  gap: var(--space-8);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  padding: var(--space-12) var(--space-16);

  strong {
    color: var(--color-text-primary);
    font-size: var(--text-body-sm);
    font-weight: var(--font-weight-medium);
    line-height: 1.6;
  }
`;

const ResourceGrid = styled.div`
  display: grid;
  gap: var(--space-8);
`;

const ResourceItem = styled.article`
  display: grid;
  gap: var(--space-8);
  border-radius: var(--radius-md);
  background: var(--color-primary-soft);
  padding: var(--space-12) var(--space-16);

  span {
    color: var(--color-text-secondary);
    font-size: var(--text-caption);
    line-height: 1.6;
  }

  strong {
    color: var(--color-text-primary);
    font-size: var(--text-body-sm);
    font-weight: var(--font-weight-medium);
    line-height: 1.6;
  }
`;
