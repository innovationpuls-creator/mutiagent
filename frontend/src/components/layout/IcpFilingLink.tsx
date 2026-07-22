import styles from "./IcpFilingLink.module.css";

const ICP_FILING_URL = "https://beian.miit.gov.cn/";

interface IcpFilingLinkProps {
	filingNumber?: string;
}

export function IcpFilingLink({
	filingNumber = import.meta.env.VITE_ICP_BEIAN_NUMBER,
}: IcpFilingLinkProps) {
	if (!filingNumber?.trim()) {
		return null;
	}

	return (
		<footer className={styles.footer}>
			<a
				className={styles.link}
				href={ICP_FILING_URL}
				target="_blank"
				rel="noreferrer"
			>
				{filingNumber}
			</a>
		</footer>
	);
}
