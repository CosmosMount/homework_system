import { readFileSync } from "node:fs";

import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

test.use({ trace: "off", video: "off" });

interface Credential {
  email: string;
  passwordFile: string;
}

function credential(role: "ADMIN" | "STUDENT"): Credential | null {
  const email = process.env[`E2E_${role}_EMAIL`];
  const passwordFile = process.env[`E2E_${role}_PASSWORD_FILE`];
  return email && passwordFile ? { email, passwordFile } : null;
}

function password(path: string): string {
  return readFileSync(path, "utf8").trim();
}

async function login(page: Page, value: Credential): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("用户名或校园邮箱").fill(value.email);
  const passwordField = page.getByLabel("密码", { exact: true });
  await passwordField.fill(password(value.passwordFile));
  try {
    await page.getByRole("button", { name: "登录", exact: true }).click();
  } finally {
    await passwordField.evaluate((element: HTMLInputElement) => {
      element.value = "";
    });
  }
  await page.waitForURL(/\/(?:admin\/)?dashboard$/);
}

const student = credential("STUDENT");
const admin = credential("ADMIN");

test("学生登录后可访问通知、作业和校内赛入口", async ({ page }) => {
  test.skip(student === null, "未提供隔离学生凭据。");
  await login(page, student!);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("欢迎回来");

  for (const [path, heading] of [
    ["/announcements", "通知"],
    ["/assignments", "培训作业"],
    ["/competitions", "校内赛"],
  ] as const) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
  }
});

test("管理员登录后可访问用户、通知、作业和赛事管理", async ({ page }) => {
  test.skip(admin === null, "未提供隔离管理员凭据。");
  await login(page, admin!);
  await expect(
    page.getByRole("heading", { name: "管理概览", level: 1 }),
  ).toBeVisible();

  for (const [path, heading] of [
    ["/admin/users", "用户管理"],
    ["/admin/announcements", "通知管理"],
    ["/admin/assignments", "作业管理"],
    ["/admin/competitions", "赛事管理"],
  ] as const) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
  }

  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(accessibility.violations).toEqual([]);
});
