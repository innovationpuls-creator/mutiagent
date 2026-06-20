import type { ReactNode } from "react";
import styled from "styled-components";
import type {
	CourseKnowledgeResult,
	CourseKnowledgeSection,
} from "../../types/chat";
import {
	getChildSections,
	getOrderedSections,
	getOutlineCourseName,
	getOutlineGradeLabel,
	getOutlineHours,
	getOutlineSummary,
	getReadableLearningSequence,
	getSectionDescription,
	getSectionHeading,
	getSectionLabel,
} from "./courseKnowledgeHelpers";

interface CourseKnowledgeCardProps {
	outline: CourseKnowledgeResult;
}

function listText(items: string[]) {
	if (items.length === 0) {
		return <EmptyText>等待进一步补充。</EmptyText>;
	}

	return (
		<InlineList>
			{items.map((item, index) => (
				<li key={`${item}-${index}`}>{item}</li>
			))}
		</InlineList>
	);
}

function renderSectionTree(
	sections: CourseKnowledgeSection[],
	parentId: string | null,
): ReactNode {
	const children = getChildSections(sections, parentId);

	if (children.length === 0) {
		return null;
	}

	return (
		<NestedStack>
			{children.map((section) => (
				<NestedCard key={section.section_id}>
					<strong>{getSectionHeading(section)}</strong>
					<p>{getSectionDescription(section)}</p>
					{listText(section.key_knowledge_points)}
					{renderSectionTree(sections, section.section_id)}
				</NestedCard>
			))}
		</NestedStack>
	);
}

export function CourseKnowledgeCard({ outline }: CourseKnowledgeCardProps) {
	const orderedSections = getOrderedSections(outline);
	const topLevelSections = orderedSections.filter(
		(section) => section.parent_section_id === null,
	);
	const learningSequence = getReadableLearningSequence(outline);

	return (
		<Card>
			<Header>
				<span>课程大纲 · {getOutlineGradeLabel(outline)}</span>
				<strong>{getOutlineCourseName(outline)}</strong>
			</Header>

			<HeroSection>
				<div>
					<SectionLabel>个性化安排</SectionLabel>
					<p>{getOutlineSummary(outline)}</p>
				</div>
				<MetaPill>{getOutlineHours(outline)}</MetaPill>
			</HeroSection>

			<Section>
				<h3>推荐学习步骤</h3>
				{listText(learningSequence)}
			</Section>

			<Section>
				<h3>章节展开</h3>
				<SectionStack>
					{topLevelSections.map((section) => {
						return (
							<SectionCard key={section.section_id}>
								<SectionHeader>
									<SectionIndex>
										{getSectionLabel(section.section_id)}
									</SectionIndex>
									<div>
										<h4>{getSectionHeading(section)}</h4>
										<p>{getSectionDescription(section)}</p>
									</div>
								</SectionHeader>

								<SectionBody>
									<SectionBlock>
										<h5>核心知识点</h5>
										{listText(section.key_knowledge_points)}
									</SectionBlock>

									{renderSectionTree(orderedSections, section.section_id)}
								</SectionBody>
							</SectionCard>
						);
					})}
				</SectionStack>
			</Section>
		</Card>
	);
}

const Card = styled.article`
  inline-size: min(100%, 44rem);
  display: grid;
  gap: var(--space-24);
  align-self: flex-start;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background:
    radial-gradient(circle at 8% 0%, oklch(84% 0.12 63 / 0.18), transparent 34%),
    linear-gradient(180deg, oklch(99% 0.008 80), oklch(97% 0.012 78));
  box-shadow: var(--shadow-md);
  padding: var(--space-24);
  color: var(--color-text-primary);
  font-family: var(--font-body);
`;

const Header = styled.header`
  display: grid;
  gap: var(--space-8);

  span {
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--color-text-whisper);
    font-size: var(--text-caption);
  }

  strong {
    font-family: var(--font-heading);
    font-size: var(--text-h3);
    font-weight: var(--font-weight-medium);
    line-height: 1.4;
  }
`;

const HeroSection = styled.section`
  display: flex;
  justify-content: space-between;
  gap: var(--space-16);
  align-items: flex-start;
  padding: var(--space-20);
  border-radius: var(--radius-md);
  background: var(--color-surface-raised);
  box-shadow: var(--shadow-sm);

  p {
    margin: var(--space-8) 0 0;
    color: var(--color-text-secondary);
    line-height: 1.8;
  }
`;

const SectionLabel = styled.span`
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-text-whisper);
  font-size: var(--text-caption);
`;

const MetaPill = styled.span`
  flex-shrink: 0;
  border-radius: var(--radius-full);
  padding: var(--space-8) var(--space-12);
  background: oklch(92% 0.03 73);
  color: oklch(38% 0.03 73);
  font-size: var(--text-caption);
`;

const Section = styled.section`
  display: grid;
  gap: var(--space-16);

  h3 {
    margin: 0;
    font-family: var(--font-heading);
    font-size: var(--text-h5);
    font-weight: var(--font-weight-medium);
  }
`;

const SectionStack = styled.div`
  display: grid;
  gap: var(--space-16);
`;

const SectionCard = styled.article`
  display: grid;
  gap: var(--space-16);
  padding: var(--space-20);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  background: oklch(99% 0.008 80 / 0.92);
  box-shadow: var(--shadow-sm);
`;

const SectionHeader = styled.div`
  display: flex;
  gap: var(--space-16);

  h4,
  p {
    margin: 0;
  }

  h4 {
    font-family: var(--font-heading);
    font-size: var(--text-body);
    font-weight: var(--font-weight-medium);
    color: var(--color-text-primary);
  }

  p {
    margin-top: var(--space-8);
    color: var(--color-text-secondary);
    line-height: 1.8;
  }
`;

const SectionIndex = styled.span`
  flex-shrink: 0;
  min-inline-size: calc(var(--space-40) + var(--space-16));
  block-size: calc(var(--space-32) + var(--space-16));
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-full);
  background: oklch(90% 0.04 73);
  color: oklch(38% 0.03 73);
  font-size: var(--text-caption);
  padding-inline: var(--space-12);
`;

const SectionBody = styled.div`
  display: grid;
  gap: var(--space-16);
`;

const SectionBlock = styled.div`
  display: grid;
  gap: var(--space-8);

  h5 {
    margin: 0;
    font-size: var(--text-caption);
    color: var(--color-text-whisper);
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
`;

const InlineList = styled.ul`
  margin: 0;
  padding-inline-start: var(--space-20);
  display: grid;
  gap: var(--space-8);

  li {
    color: var(--color-text-secondary);
    line-height: 1.8;
  }
`;

const NestedStack = styled.div`
  display: grid;
  gap: var(--space-12);
`;

const NestedCard = styled.div`
  display: grid;
  gap: var(--space-8);
  padding: var(--space-16);
  border-radius: var(--radius-md);
  background: oklch(97% 0.01 80);
  border: 1px solid var(--color-border-subtle);

  strong {
    font-size: var(--text-body-sm);
    color: var(--color-text-primary);
  }

  p {
    margin: 0;
    color: var(--color-text-secondary);
    line-height: 1.7;
  }
`;

const EmptyText = styled.p`
  margin: 0;
  color: var(--color-text-muted);
  font-size: var(--text-body-sm);
`;
