import { motion } from "framer-motion";
import React from "react";
import styled from "styled-components";

interface Props {
	layoutId?: string;
	isHappy?: boolean;
}

export function AiEyes({ layoutId, isHappy = false }: Props) {
	return (
		<EyesWrapper
			as={motion.div}
			layoutId={layoutId}
			className={isHappy ? "eyes happy" : "eyes"}
		>
			{isHappy ? (
				<>
					<svg fill="none" viewBox="0 0 24 24">
						<path
							fill="currentColor"
							d="M8.28386 16.2843C8.9917 15.7665 9.8765 14.731 12 14.731C14.1235 14.731 15.0083 15.7665 15.7161 16.2843C17.8397 17.8376 18.7542 16.4845 18.9014 15.7665C19.4323 13.1777 17.6627 11.1066 17.3088 10.5888C16.3844 9.23666 14.1235 8 12 8C9.87648 8 7.61556 9.23666 6.69122 10.5888C6.33728 11.1066 4.56771 13.1777 5.09858 15.7665C5.24582 16.4845 6.16034 17.8376 8.28386 16.2843Z"
						/>
					</svg>
					<svg fill="none" viewBox="0 0 24 24">
						<path
							fill="currentColor"
							d="M8.28386 16.2843C8.9917 15.7665 9.8765 14.731 12 14.731C14.1235 14.731 15.0083 15.7665 15.7161 16.2843C17.8397 17.8376 18.7542 16.4845 18.9014 15.7665C19.4323 13.1777 17.6627 11.1066 17.3088 10.5888C16.3844 9.23666 14.1235 8 12 8C9.87648 8 7.61556 9.23666 6.69122 10.5888C6.33728 11.1066 4.56771 13.1777 5.09858 15.7665C5.24582 16.4845 6.16034 17.8376 8.28386 16.2843Z"
						/>
					</svg>
				</>
			) : (
				<>
					<span className="eye" />
					<span className="eye" />
				</>
			)}
		</EyesWrapper>
	);
}

const EyesWrapper = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  height: 52px;
  gap: 2rem;
  
  &.happy { gap: 0; svg { width: 60px; color: var(--color-text-primary, #fff); } }
  
  & .eye {
    width: 26px;
    height: 52px;
    background-color: var(--color-text-primary, #fff);
    border-radius: 16px;
    animation: animate-eyes 10s infinite linear;
  }

  @keyframes animate-eyes {
    46% { height: 52px; }
    48% { height: 20px; }
    50% { height: 52px; }
    96% { height: 52px; }
    98% { height: 20px; }
    100% { height: 52px; }
  }
`;
