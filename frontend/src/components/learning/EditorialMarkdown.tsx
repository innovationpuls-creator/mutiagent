import React from "react";
import { MarkdownRenderer } from "../markdown";

interface EditorialMarkdownProps {
	content: string;
}

export function EditorialMarkdown({ content }: EditorialMarkdownProps) {
	return <MarkdownRenderer content={content} variant="editorial" />;
}
