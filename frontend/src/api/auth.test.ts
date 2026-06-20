import { describe, expect, it } from "vitest";
import { extractErrorMessage } from "./auth";

describe("extractErrorMessage", () => {
	it("uses FastAPI string details directly", () => {
		expect(extractErrorMessage({ detail: "账号或密码不正确" })).toBe(
			"账号或密码不正确",
		);
	});

	it("turns FastAPI validation details into Chinese copy", () => {
		expect(
			extractErrorMessage({
				detail: [
					{ msg: "String should have at least 6 characters" },
					{ msg: "两次输入的密码不一致" },
				],
			}),
		).toBe("表单信息不完整，请检查长度和必填项后重试");
	});
});
