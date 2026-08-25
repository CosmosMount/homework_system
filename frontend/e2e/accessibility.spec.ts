import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const viewports = [
  { width: 360, height: 800 },
  { width: 768, height: 1024 },
  { width: 1280, height: 900 },
  { width: 1440, height: 900 },
];

test("认证页支持键盘、可见焦点、四档响应式与 WCAG 2.1 AA", async ({
  page,
}) => {
  await page.goto("/login");
  await expect(
    page.getByRole("heading", { name: "登录训练平台", level: 1 }),
  ).toBeVisible();

  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    await expect(page.locator("body")).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(overflow, `页面在 ${viewport.width}px 不应横向溢出`).toBeFalsy();
  }

  await page.setViewportSize(viewports[0]);
  await page.keyboard.press("Tab");
  const focused = page.locator(":focus");
  await expect(focused).toBeVisible();
  const outline = await focused.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      outlineStyle: style.outlineStyle,
      outlineWidth: style.outlineWidth,
      boxShadow: style.boxShadow,
    };
  });
  expect(
    outline.outlineStyle !== "none" ||
      outline.outlineWidth !== "0px" ||
      outline.boxShadow !== "none",
  ).toBeTruthy();

  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(accessibility.violations).toEqual([]);
});

test("减少动态效果偏好不会阻断认证流程", async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: "reduce" });
  const page = await context.newPage();
  await page.goto("/register");
  await expect(
    page.getByRole("heading", { name: "创建学生账号", level: 1 }),
  ).toBeVisible();
  await context.close();
});
