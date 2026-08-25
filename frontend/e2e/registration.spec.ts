import { expect, test } from "@playwright/test";

test.use({ trace: "off", video: "off" });

test("学生可通过校园邮箱完成注册提交", async ({ browserName, page }, testInfo) => {
  test.skip(process.env.E2E_RUN_MUTATIONS !== "1", "未启用隔离写入场景。");
  test.skip(browserName !== "chromium", "注册写入仅执行一次，读路径保持三浏览器覆盖。");
  const suffix = testInfo.project.name.replace(/[^a-z0-9]/gi, "").toLowerCase();
  const runId = process.env.E2E_REGISTRATION_RUN_ID?.replace(/[^a-z0-9]/gi, "").toLowerCase();
  const passwordFile = process.env.E2E_REGISTRATION_PASSWORD_FILE;
  if (!passwordFile || !runId) {
    throw new Error(
      "E2E_RUN_MUTATIONS=1 时必须提供注册密码文件和唯一运行标识。",
    );
  }
  const { readFileSync } = await import("node:fs");
  const password = readFileSync(passwordFile, "utf8").trim();

  await page.goto("/register");
  await page.getByLabel("真实姓名").fill(`虚构注册学生-${suffix}`);
  await page.getByLabel("学号").fill(`E2E-REG-${runId}-${suffix}`);
  await page
    .getByLabel("校园邮箱")
    .fill(`e2e-register-${runId}-${suffix}@connect.hkust-gz.edu.cn`);
  const passwordField = page.getByLabel("密码", { exact: true });
  await passwordField.fill(password);
  try {
    await page.getByRole("button", { name: "创建账号" }).click();
  } finally {
    await passwordField.evaluate((element: HTMLInputElement) => {
      element.value = "";
    });
  }

  await expect(
    page.getByText("注册成功。验证邮件已进入发送队列"),
  ).toBeVisible();
});
