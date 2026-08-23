import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import LoginPage from "@/app/login/page";

describe("login page skeleton", () => {
  it("shows accessible fields without pretending authentication is ready", () => {
    render(<LoginPage />);

    expect(
      screen.getByRole("heading", { name: "登录训练平台" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("校园邮箱")).toHaveAttribute(
      "placeholder",
      "name@hkust-gz.edu.cn",
    );
    expect(screen.getByLabelText("密码")).toHaveAttribute("type", "password");
    expect(
      screen.getByRole("button", { name: "登录服务尚未接入" }),
    ).toBeDisabled();
  });
});
