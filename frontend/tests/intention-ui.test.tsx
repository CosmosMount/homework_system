import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { IntentionAdminPanel } from "@/components/admin/intention-admin-panel";
import { IntentionForm } from "@/components/intentions/intention-form";
import type {
  AdminIntentionSurvey,
  AdminIntentionSurveyDetail,
  Direction,
  IntentionSurvey,
} from "@/lib/api/types";

const { apiFetchMock, csrfFetchMock, qrToDataUrlMock, refreshMock } = vi.hoisted(
  () => ({
    apiFetchMock: vi.fn(),
    csrfFetchMock: vi.fn(),
    qrToDataUrlMock: vi.fn(),
    refreshMock: vi.fn(),
  }),
);

vi.mock("next/navigation", () => ({
  usePathname: () => "/intentions",
  useRouter: () => ({ refresh: refreshMock, replace: vi.fn() }),
}));

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  apiFetch: apiFetchMock,
  csrfFetch: csrfFetchMock,
}));

vi.mock("qrcode", () => ({
  default: { toDataURL: qrToDataUrlMock },
}));

function intention(overrides: Partial<IntentionSurvey> = {}): IntentionSurvey {
  return {
    id: "survey-1",
    title: "培训方向问卷",
    description_html: "<p>请选择培训方向</p>",
    status: "open",
    starts_at: null,
    ends_at: null,
    question_count: 2,
    has_response: false,
    submissions_used: 0,
    max_submissions: 2,
    questions: [
      {
        id: "question-first",
        prompt: "第一志愿",
        allow_multiple: false,
        display_order: 0,
        options: [
          { id: "option-robot", label: "机器人", display_order: 0 },
          { id: "option-vision", label: "视觉", display_order: 1 },
        ],
      },
      {
        id: "question-second",
        prompt: "第二志愿",
        allow_multiple: true,
        display_order: 1,
        options: [
          { id: "option-control", label: "电控", display_order: 0 },
          { id: "option-embedded", label: "嵌入式", display_order: 1 },
        ],
      },
    ],
    response: null,
    revision: 1,
    ...overrides,
  };
}

function adminSurvey(
  overrides: Partial<AdminIntentionSurvey> = {},
): AdminIntentionSurvey {
  return {
    id: "survey-1",
    title: "培训方向问卷",
    description_markdown: "请选择",
    status: "draft",
    starts_at: null,
    ends_at: null,
    question_count: 2,
    responded_count: 0,
    max_submissions: 2,
    audience: {
      all_students: true,
      direction_ids: [],
    },
    created_at: "2026-08-27T00:00:00Z",
    updated_at: "2026-08-27T00:00:00Z",
    revision: 1,
    ...overrides,
  };
}

function direction(overrides: Partial<Direction> = {}): Direction {
  return {
    id: "direction-1",
    code: "robotics",
    name: "机器人组",
    description: null,
    is_active: true,
    revision: 1,
    ...overrides,
  };
}

function adminDetail(
  overrides: Partial<AdminIntentionSurveyDetail> = {},
): AdminIntentionSurveyDetail {
  return {
    ...adminSurvey(),
    questions: [
      {
        id: "question-first",
        prompt: "第一志愿",
        allow_multiple: false,
        display_order: 0,
        options: [
          { id: "option-robot", label: "机器人", display_order: 0 },
          { id: "option-vision", label: "视觉", display_order: 1 },
        ],
      },
      {
        id: "question-second",
        prompt: "第二志愿",
        allow_multiple: true,
        display_order: 1,
        options: [
          { id: "option-control", label: "电控", display_order: 0 },
          { id: "option-embedded", label: "嵌入式", display_order: 1 },
        ],
      },
    ],
    ...overrides,
  };
}

describe("student questionnaire form", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    csrfFetchMock.mockReset();
    qrToDataUrlMock.mockReset();
    refreshMock.mockReset();
  });

  it("submits every single and multiple choice question", async () => {
    csrfFetchMock.mockResolvedValue({
      answers: [
        {
          question_id: "question-first",
          selected_option_ids: ["option-vision"],
        },
        {
          question_id: "question-second",
          selected_option_ids: ["option-control", "option-embedded"],
        },
      ],
      free_text: "希望参与视觉组",
      submitted_at: "2026-08-28T01:00:00Z",
      submission_count: 1,
    });
    render(<IntentionForm initialSurvey={intention()} />);

    fireEvent.click(screen.getByLabelText("视觉"));
    fireEvent.click(screen.getByLabelText("电控"));
    fireEvent.click(screen.getByLabelText("嵌入式"));
    fireEvent.change(screen.getByLabelText("补充说明（可选）"), {
      target: { value: "  希望参与视觉组  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交问卷" }));

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledTimes(1));
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/intentions/survey-1/response",
      {
        method: "PUT",
        body: JSON.stringify({
          answers: [
            {
              question_id: "question-first",
              selected_option_ids: ["option-vision"],
            },
            {
              question_id: "question-second",
              selected_option_ids: ["option-control", "option-embedded"],
            },
          ],
          free_text: "希望参与视觉组",
        }),
      },
    );
    expect(screen.getByText(/还可提交 1 次/)).toBeInTheDocument();
  });

  it("shows the latest answers and becomes read-only at the submission limit", () => {
    render(
      <IntentionForm
        initialSurvey={
          intention({
            has_response: true,
            submissions_used: 2,
            response: {
              answers: [
                {
                  question_id: "question-first",
                  selected_option_ids: ["option-robot"],
                },
                {
                  question_id: "question-second",
                  selected_option_ids: ["option-control"],
                },
              ],
              free_text: null,
              submitted_at: "2026-08-27T01:00:00Z",
              submission_count: 2,
            },
          })
        }
      />,
    );

    expect(screen.getByLabelText("机器人")).toBeChecked();
    expect(screen.getByLabelText("电控")).toBeChecked();
    expect(screen.getByRole("button", { name: "再次提交问卷" })).toBeDisabled();
    expect(screen.getByText(/提交次数已经用完/)).toBeInTheDocument();
  });
});

describe("administrator questionnaire panel", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    csrfFetchMock.mockReset();
    qrToDataUrlMock.mockReset();
    refreshMock.mockReset();
  });

  it("creates a multi-question questionnaire with a submission limit", async () => {
    csrfFetchMock.mockResolvedValue(adminSurvey({ id: "survey-created" }));
    render(<IntentionAdminPanel initialSurveys={[]} />);

    fireEvent.change(screen.getByLabelText("问卷标题"), {
      target: { value: "  组队岗位意向  " },
    });
    const prompts = screen.getAllByLabelText("题目");
    const options = screen.getAllByLabelText("选项（每行一个）");
    const multiple = screen.getAllByLabelText("本题允许多选");
    fireEvent.change(prompts[0]!, { target: { value: "第一志愿" } });
    fireEvent.change(options[0]!, { target: { value: "机械\n视觉" } });
    fireEvent.change(prompts[1]!, { target: { value: "第二志愿" } });
    fireEvent.change(options[1]!, { target: { value: "电控\n嵌入式" } });
    fireEvent.click(multiple[1]!);
    fireEvent.change(screen.getByLabelText("每人最多提交次数"), {
      target: { value: "3" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建问卷" }));

    await screen.findByText("问卷已创建。开放填写后学生即可提交。");
    expect(csrfFetchMock).toHaveBeenCalledWith("/admin/intentions", {
      method: "POST",
      body: JSON.stringify({
        title: "组队岗位意向",
        description_markdown: "",
        questions: [
          {
            prompt: "第一志愿",
            allow_multiple: false,
            options: [{ label: "机械" }, { label: "视觉" }],
          },
          {
            prompt: "第二志愿",
            allow_multiple: true,
            options: [{ label: "电控" }, { label: "嵌入式" }],
          },
        ],
        max_submissions: 3,
        audience: {
          all_students: true,
          direction_ids: [],
        },
      }),
    });
  });

  it("creates and displays a questionnaire for selected technical directions", async () => {
    const directions = [
      direction(),
      direction({ id: "direction-2", code: "vision", name: "视觉组" }),
    ];
    csrfFetchMock.mockResolvedValue(
      adminSurvey({
        id: "survey-created",
        title: "分组问卷",
        audience: {
          all_students: false,
          direction_ids: ["direction-1", "direction-2"],
        },
      }),
    );
    render(<IntentionAdminPanel directions={directions} initialSurveys={[]} />);

    fireEvent.change(screen.getByLabelText("问卷标题"), {
      target: { value: "分组问卷" },
    });
    fireEvent.click(
      screen.getByRole("radio", { name: "指定技术组填写" }),
    );
    fireEvent.click(screen.getByLabelText("问卷受众：机器人组"));
    fireEvent.click(screen.getByLabelText("问卷受众：视觉组"));
    fireEvent.click(screen.getByRole("button", { name: "创建问卷" }));

    await screen.findByText("问卷已创建。开放填写后学生即可提交。");
    const request = csrfFetchMock.mock.calls[0]?.[1] as { body: string };
    expect(JSON.parse(request.body).audience).toEqual({
      all_students: false,
      direction_ids: ["direction-1", "direction-2"],
    });
    const card = screen.getByRole("heading", { name: "分组问卷" }).closest("article");
    expect(card).toHaveTextContent("填写范围：机器人组、视觉组");
  });

  it("opens a questionnaire, generates a local QR code, and closes it", async () => {
    const draft = adminSurvey();
    const opened = adminSurvey({ status: "open", revision: 2 });
    const closed = adminSurvey({ status: "closed", revision: 3 });
    csrfFetchMock
      .mockResolvedValueOnce(opened)
      .mockResolvedValueOnce({
        survey_id: draft.id,
        token: "qr-token",
        fill_url: "https://training.invalid/intentions/survey-1?token=qr-token",
        generated_at: "2026-08-27T02:00:00Z",
      })
      .mockResolvedValueOnce(closed);
    qrToDataUrlMock.mockResolvedValue("data:image/png;base64,qr-image");
    render(<IntentionAdminPanel initialSurveys={[draft]} />);

    fireEvent.click(screen.getByRole("button", { name: "开放填写" }));
    await screen.findByText("问卷状态已更新为“开放中”。");
    fireEvent.click(screen.getByRole("button", { name: "生成二维码" }));

    await screen.findByAltText("培训方向问卷移动端填写二维码");
    expect(qrToDataUrlMock).toHaveBeenCalledWith(
      "https://training.invalid/intentions/survey-1?token=qr-token",
      expect.objectContaining({ width: 280 }),
    );
    fireEvent.click(screen.getByRole("button", { name: "关闭问卷" }));
    await screen.findByText("问卷状态已更新为“已关闭”。");
    expect(
      screen.queryByRole("button", { name: "生成二维码" }),
    ).not.toBeInTheDocument();
  });

  it("reopens a closed questionnaire without exposing archive as reversible", async () => {
    const closed = adminSurvey({ status: "closed", revision: 3 });
    const reopened = adminSurvey({ status: "open", revision: 4 });
    csrfFetchMock.mockResolvedValueOnce(reopened);
    render(<IntentionAdminPanel initialSurveys={[closed]} />);

    expect(
      screen.getByRole("button", { name: "归档问卷" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新开启" }));

    await screen.findByText("问卷状态已更新为“开放中”。");
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/admin/intentions/survey-1/open",
      { method: "POST" },
    );
    expect(
      screen.getByRole("button", { name: "关闭问卷" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "生成二维码" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "重新开启" }),
    ).not.toBeInTheDocument();
  });

  it("keeps all questionnaire commands on one row at the desktop breakpoint", () => {
    const survey = adminSurvey({ status: "open" });
    render(<IntentionAdminPanel initialSurveys={[survey]} />);

    const commandGroup = screen.getByRole("group", {
      name: `问卷“${survey.title}”操作`,
    });
    expect(commandGroup).toHaveClass("flex-wrap", "lg:flex-nowrap");
    for (const name of [
      "关闭问卷",
      "生成二维码",
      "查看统计",
      "查看提交名单",
      "查看内容",
      "编辑问卷",
      "删除问卷",
    ]) {
      const command = within(commandGroup).getByRole("button", { name });
      expect(command).toBeInTheDocument();
      expect(command).toHaveClass("shrink-0", "whitespace-nowrap");
    }
  });

  it("keeps a questionnaire when permanent deletion is cancelled", () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<IntentionAdminPanel initialSurveys={[adminSurvey()]} />);

    fireEvent.click(screen.getByRole("button", { name: "删除问卷" }));

    expect(confirm).toHaveBeenCalledWith(
      expect.stringContaining("题目、选项和全部学生回答将一并删除"),
    );
    expect(csrfFetchMock).not.toHaveBeenCalled();
    expect(
      screen.getByRole("heading", { name: "培训方向问卷" }),
    ).toBeInTheDocument();
    confirm.mockRestore();
  });

  it("permanently deletes a questionnaire and removes its card immediately", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    csrfFetchMock.mockResolvedValue(undefined);
    const removed = adminSurvey();
    const retained = adminSurvey({ id: "survey-2", title: "保留问卷" });
    render(<IntentionAdminPanel initialSurveys={[removed, retained]} />);

    const removedCard = screen
      .getByRole("heading", { name: removed.title })
      .closest("article");
    expect(removedCard).not.toBeNull();
    fireEvent.click(
      within(removedCard!).getByRole("button", { name: "删除问卷" }),
    );

    await screen.findByText("问卷已永久删除。");
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/admin/intentions/survey-1",
      { method: "DELETE" },
    );
    expect(
      screen.queryByRole("heading", { name: removed.title }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: retained.title }),
    ).toBeInTheDocument();
    confirm.mockRestore();
  });

  it("keeps the questionnaire card when permanent deletion fails", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    csrfFetchMock.mockRejectedValue(new Error("network unavailable"));
    render(<IntentionAdminPanel initialSurveys={[adminSurvey()]} />);

    fireEvent.click(screen.getByRole("button", { name: "删除问卷" }));

    await screen.findByText("操作失败，请稍后重试。");
    expect(
      screen.getByRole("heading", { name: "培训方向问卷" }),
    ).toBeInTheDocument();
    confirm.mockRestore();
  });

  it("searches active students and sends email only to selected members", async () => {
    apiFetchMock.mockResolvedValue({
      page: 1,
      page_size: 20,
      total: 1,
      items: [
        {
          id: "student-1",
          email: "student@connect.hkust-gz.edu.cn",
          full_name: "测试学生",
          student_number: "20260001",
          role: "student",
          status: "active",
          team_id: null,
          team_name: null,
          created_at: "2026-08-27T00:00:00Z",
        },
      ],
    });
    csrfFetchMock.mockResolvedValue({
      survey_id: "survey-1",
      requested_count: 1,
      queued_count: 1,
      already_queued_count: 0,
    });
    render(
      <IntentionAdminPanel initialSurveys={[adminSurvey({ status: "open" })]} />,
    );

    const sendButton = screen.getByRole("button", {
      name: "向已选成员发送邮件",
    });
    expect(sendButton).toBeDisabled();

    fireEvent.change(screen.getByLabelText("搜索成员"), {
      target: { value: "测试学生" },
    });
    fireEvent.click(screen.getByRole("button", { name: "搜索成员" }));

    const student = await screen.findByLabelText(/测试学生/);
    fireEvent.click(student);
    fireEvent.click(sendButton);

    await screen.findByText("已为 1 名成员创建邮件任务。");
    expect(apiFetchMock).toHaveBeenCalledWith(
      "/admin/users?page=1&page_size=20&status=active&role=student&search=%E6%B5%8B%E8%AF%95%E5%AD%A6%E7%94%9F",
    );
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/admin/intentions/survey-1/email-notifications",
      {
        method: "POST",
        headers: { "Idempotency-Key": expect.any(String) },
        body: JSON.stringify({
          recipient_scope: "manual",
          recipient_user_ids: ["student-1"],
        }),
      },
    );
  });

  it("sends email to multiple active technical directions", async () => {
    csrfFetchMock.mockResolvedValue({
      survey_id: "survey-1",
      requested_count: 5,
      queued_count: 5,
      already_queued_count: 0,
    });
    render(
      <IntentionAdminPanel
        directions={[
          direction(),
          direction({
            id: "direction-2",
            code: "vision",
            name: "视觉组",
          }),
          direction({
            id: "direction-inactive",
            code: "inactive",
            name: "停用技术组",
            is_active: false,
          }),
        ]}
        initialSurveys={[adminSurvey({ status: "open" })]}
      />,
    );

    fireEvent.click(screen.getByRole("radio", { name: "按技术组" }));
    expect(
      screen.queryByRole("checkbox", { name: "停用技术组" }),
    ).not.toBeInTheDocument();
    const sendButton = screen.getByRole("button", {
      name: "向已选技术组发送邮件",
    });
    expect(sendButton).toBeDisabled();

    fireEvent.click(screen.getByRole("checkbox", { name: "机器人组" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "视觉组" }));
    expect(sendButton).toBeEnabled();
    fireEvent.click(sendButton);

    await screen.findByText("已为 5 名成员创建邮件任务。");
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/admin/intentions/survey-1/email-notifications",
      {
        method: "POST",
        headers: { "Idempotency-Key": expect.any(String) },
        body: JSON.stringify({
          recipient_scope: "direction",
          direction_ids: ["direction-1", "direction-2"],
        }),
      },
    );
  });

  it("limits direction and all-email scopes to the questionnaire audience", async () => {
    csrfFetchMock.mockResolvedValue({
      survey_id: "survey-1",
      requested_count: 2,
      queued_count: 2,
      already_queued_count: 0,
    });
    render(
      <IntentionAdminPanel
        directions={[
          direction(),
          direction({ id: "direction-2", code: "vision", name: "视觉组" }),
        ]}
        initialSurveys={[
          adminSurvey({
            status: "open",
            audience: {
              all_students: false,
              direction_ids: ["direction-1"],
            },
          }),
        ]}
      />,
    );

    expect(
      screen.getByRole("radio", { name: "问卷全部目标学生" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "按技术组" }));
    expect(
      screen.getByRole("checkbox", { name: "机器人组" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("checkbox", { name: "视觉组" }),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("radio", { name: "问卷全部目标学生" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "向问卷全部目标学生发送邮件" }),
    );

    await screen.findByText("已为 2 名成员创建邮件任务。");
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/admin/intentions/survey-1/email-notifications",
      {
        method: "POST",
        headers: { "Idempotency-Key": expect.any(String) },
        body: JSON.stringify({ recipient_scope: "all" }),
      },
    );
  });

  it("sends email to all active students", async () => {
    csrfFetchMock.mockResolvedValue({
      survey_id: "survey-1",
      requested_count: 158,
      queued_count: 157,
      already_queued_count: 1,
    });
    render(
      <IntentionAdminPanel initialSurveys={[adminSurvey({ status: "open" })]} />,
    );

    fireEvent.click(screen.getByRole("radio", { name: "全部激活学生" }));
    const sendButton = screen.getByRole("button", {
      name: "向全部激活学生发送邮件",
    });
    expect(sendButton).toBeEnabled();
    fireEvent.click(sendButton);

    await screen.findByText(
      "已新增 157 封邮件任务；1 名成员本次开放周期已入队，未重复发送。",
    );
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/admin/intentions/survey-1/email-notifications",
      {
        method: "POST",
        headers: { "Idempotency-Key": expect.any(String) },
        body: JSON.stringify({ recipient_scope: "all" }),
      },
    );
  });

  it("shows per-question aggregate statistics", async () => {
    apiFetchMock.mockResolvedValue({
      survey_id: "survey-1",
      total_active_students: 8,
      responded_count: 2,
      response_rate: 25,
      questions: [
        {
          question_id: "question-first",
          prompt: "第一志愿",
          allow_multiple: false,
          options: [
            {
              option_id: "option-robot",
              label: "机器人",
              response_count: 1,
              percentage: 50,
            },
          ],
        },
      ],
    });
    render(
      <IntentionAdminPanel initialSurveys={[adminSurvey({ status: "open" })]} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "查看统计" }));

    expect(await screen.findByText(/提交率 25%/)).toBeInTheDocument();
    expect(screen.getByText("1. 第一志愿（单选）")).toBeInTheDocument();
    expect(screen.getByText("1 · 50%")).toBeInTheDocument();
    expect(
      screen.getByRole("progressbar", {
        name: "第一志愿 / 机器人选择比例",
      }),
    ).toHaveAttribute("aria-valuenow", "50");
  });

  it("shows the identified latest-response roster only to the admin panel", async () => {
    apiFetchMock.mockResolvedValue({
      survey_id: "survey-1",
      total: 1,
      items: [
        {
          user_id: "student-1",
          full_name: "测试学生",
          student_number: "20260001",
          email: "student@connect.hkust-gz.edu.cn",
          answers: [
            {
              question_id: "question-first",
              prompt: "第一志愿",
              selected_options: ["视觉"],
            },
          ],
          free_text: "愿意调剂",
          submission_count: 2,
          submitted_at: "2026-08-28T02:00:00Z",
        },
      ],
    });
    render(
      <IntentionAdminPanel initialSurveys={[adminSurvey({ status: "open" })]} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "查看提交名单" }));

    expect(await screen.findByText("测试学生")).toBeInTheDocument();
    expect(screen.getByText(/20260001/)).toBeInTheDocument();
    expect(screen.getByText("视觉")).toBeInTheDocument();
    expect(screen.getByText(/提交 2 次/)).toBeInTheDocument();
  });

  it("loads complete content and exposes editing for an open questionnaire", async () => {
    const opened = adminDetail({ status: "open", revision: 2 });
    apiFetchMock.mockResolvedValue(opened);
    render(
      <IntentionAdminPanel
        initialSurveys={[adminSurvey({ status: "open", revision: 2 })]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "查看内容" }));

    expect(
      await screen.findByRole("heading", { name: "问卷内容" }),
    ).toBeInTheDocument();
    expect(apiFetchMock).toHaveBeenCalledWith("/admin/intentions/survey-1");
    expect(screen.getByText("1. 第一志愿（单选）")).toBeInTheDocument();
    expect(screen.getByText("机器人")).toBeInTheDocument();
    expect(screen.getByText("2. 第二志愿（多选）")).toBeInTheDocument();
    expect(
      screen.getByText(/可修改标题、说明、题目文字、提交限制、时间窗口和填写范围/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "编辑问卷" }),
    ).toBeInTheDocument();
  });

  it("edits open questionnaire text and settings while answer structure stays read-only", async () => {
    const opened = adminDetail({
      status: "open",
      revision: 2,
      audience: {
        all_students: false,
        direction_ids: ["direction-1"],
      },
    });
    const updated = adminDetail({
      ...opened,
      title: "开放中的新标题",
      revision: 3,
      questions: [
        { ...opened.questions[0]!, prompt: "首选技术组" },
        opened.questions[1]!,
      ],
    });
    apiFetchMock.mockResolvedValue(opened);
    csrfFetchMock.mockResolvedValue(updated);
    render(
      <IntentionAdminPanel
        directions={[direction()]}
        initialSurveys={[
          adminSurvey({
            status: "open",
            revision: 2,
            audience: opened.audience,
          }),
        ]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "编辑问卷" }));

    const editHeading = await screen.findByRole("heading", { name: "编辑问卷" });
    const editForm = editHeading.closest("form");
    expect(editForm).not.toBeNull();
    expect(
      within(editForm!).getByText(/题目数量、题型和选项已冻结，已有回答不会删除/),
    ).toBeInTheDocument();
    expect(within(editForm!).getByLabelText("编辑选项 1")).toHaveProperty(
      "readOnly",
      true,
    );
    expect(
      within(editForm!).getByLabelText("编辑第 1 题允许多选"),
    ).toBeDisabled();
    expect(
      within(editForm!).queryByRole("button", { name: "添加题目" }),
    ).not.toBeInTheDocument();
    expect(
      within(editForm!).queryByRole("button", { name: "删除本题" }),
    ).not.toBeInTheDocument();

    fireEvent.change(within(editForm!).getByLabelText("编辑问卷标题"), {
      target: { value: "  开放中的新标题  " },
    });
    fireEvent.change(within(editForm!).getByLabelText("编辑题目 1"), {
      target: { value: "首选技术组" },
    });
    fireEvent.click(within(editForm!).getByRole("button", { name: "保存修改" }));

    await screen.findByText("问卷修改已保存。");
    expect(csrfFetchMock).toHaveBeenCalledWith("/admin/intentions/survey-1", {
      method: "PATCH",
      body: JSON.stringify({
        revision: 2,
        title: "开放中的新标题",
        description_markdown: "请选择",
        questions: [
          {
            prompt: "首选技术组",
            allow_multiple: false,
            options: [{ label: "机器人" }, { label: "视觉" }],
          },
          {
            prompt: "第二志愿",
            allow_multiple: true,
            options: [{ label: "电控" }, { label: "嵌入式" }],
          },
        ],
        max_submissions: 2,
        audience: {
          all_students: false,
          direction_ids: ["direction-1"],
        },
        starts_at: null,
        ends_at: null,
      }),
    });
    expect(screen.getByText("1. 首选技术组（单选）")).toBeInTheDocument();
  });

  it("allows closed questionnaires to edit but keeps archived questionnaires read-only", async () => {
    const { unmount } = render(
      <IntentionAdminPanel
        initialSurveys={[adminSurvey({ status: "closed", revision: 3 })]}
      />,
    );

    expect(
      screen.getByRole("button", { name: "编辑问卷" }),
    ).toBeInTheDocument();

    unmount();
    apiFetchMock.mockResolvedValue(adminDetail({ status: "archived", revision: 4 }));
    render(
      <IntentionAdminPanel
        initialSurveys={[adminSurvey({ status: "archived", revision: 4 })]}
      />,
    );
    expect(
      screen.queryByRole("button", { name: "编辑问卷" }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "查看内容" }));
    expect(await screen.findByText("已归档问卷只能查看，不能再修改。")).toBeInTheDocument();
  });

  it("edits a draft questionnaire and refreshes its visible content", async () => {
    const draftDetail = adminDetail();
    const updated = adminDetail({
      title: "更新后的培训方向问卷",
      description_markdown: "更新说明",
      max_submissions: 3,
      revision: 2,
      audience: {
        all_students: false,
        direction_ids: ["direction-1", "direction-2"],
      },
      questions: [
        {
          id: "question-new-first",
          prompt: "首选方向",
          allow_multiple: false,
          display_order: 0,
          options: [
            { id: "option-new-robot", label: "机器人", display_order: 0 },
            { id: "option-new-vision", label: "视觉", display_order: 1 },
            { id: "option-new-mechanical", label: "机械", display_order: 2 },
          ],
        },
        draftDetail.questions[1]!,
      ],
    });
    apiFetchMock.mockResolvedValue(draftDetail);
    csrfFetchMock.mockResolvedValue(updated);
    render(
      <IntentionAdminPanel
        directions={[
          direction(),
          direction({ id: "direction-2", code: "vision", name: "视觉组" }),
        ]}
        initialSurveys={[adminSurvey()]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "编辑问卷" }));
    const editHeading = await screen.findByRole("heading", { name: "编辑问卷" });
    const editForm = editHeading.closest("form");
    expect(editForm).not.toBeNull();
    const titleInput = within(editForm!).getByLabelText("编辑问卷标题");
    fireEvent.change(titleInput, {
      target: { value: "  更新后的培训方向问卷  " },
    });
    fireEvent.change(screen.getByLabelText("编辑说明（Markdown，可选）"), {
      target: { value: "更新说明" },
    });
    fireEvent.change(screen.getByLabelText("编辑题目 1"), {
      target: { value: "首选方向" },
    });
    fireEvent.change(screen.getByLabelText("编辑选项 1"), {
      target: { value: "机器人\n视觉\n机械" },
    });
    fireEvent.change(screen.getByLabelText("编辑每人最多提交次数"), {
      target: { value: "3" },
    });
    fireEvent.click(
      within(editForm!).getByRole("radio", { name: "指定技术组填写" }),
    );
    fireEvent.click(screen.getByLabelText("编辑问卷受众：机器人组"));
    fireEvent.click(screen.getByLabelText("编辑问卷受众：视觉组"));
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    await screen.findByText("问卷修改已保存。");
    expect(csrfFetchMock).toHaveBeenCalledWith("/admin/intentions/survey-1", {
      method: "PATCH",
      body: JSON.stringify({
        revision: 1,
        title: "更新后的培训方向问卷",
        description_markdown: "更新说明",
        questions: [
          {
            prompt: "首选方向",
            allow_multiple: false,
            options: [{ label: "机器人" }, { label: "视觉" }, { label: "机械" }],
          },
          {
            prompt: "第二志愿",
            allow_multiple: true,
            options: [{ label: "电控" }, { label: "嵌入式" }],
          },
        ],
        max_submissions: 3,
        audience: {
          all_students: false,
          direction_ids: ["direction-1", "direction-2"],
        },
        starts_at: null,
        ends_at: null,
      }),
    });
    expect(screen.getByText("1. 首选方向（单选）")).toBeInTheDocument();
    expect(screen.getByText("机械")).toBeInTheDocument();
    const content = screen
      .getByRole("heading", { name: "问卷内容" })
      .closest("section");
    expect(content).toHaveTextContent("填写范围：机器人组、视觉组");
  });

  it("lets an admin remove a selected direction that became inactive", async () => {
    const draftDetail = adminDetail({
      audience: {
        all_students: false,
        direction_ids: ["direction-1"],
      },
    });
    const updated = adminDetail({
      revision: 2,
      audience: {
        all_students: false,
        direction_ids: ["direction-2"],
      },
    });
    apiFetchMock.mockResolvedValue(draftDetail);
    csrfFetchMock.mockResolvedValue(updated);
    render(
      <IntentionAdminPanel
        directions={[
          direction({ is_active: false }),
          direction({ id: "direction-2", code: "vision", name: "视觉组" }),
        ]}
        initialSurveys={[
          adminSurvey({
            audience: {
              all_students: false,
              direction_ids: ["direction-1"],
            },
          }),
        ]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "编辑问卷" }));
    const inactiveDirection = await screen.findByLabelText(
      "编辑问卷受众：机器人组",
    );
    expect(inactiveDirection).toBeChecked();
    expect(screen.getByText("机器人组（已停用）")).toBeInTheDocument();
    expect(
      screen.getByText("已停用的原受众不能继续保留，请取消选择后再保存。"),
    ).toBeInTheDocument();

    fireEvent.click(inactiveDirection);
    expect(
      screen.queryByLabelText("编辑问卷受众：机器人组"),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("编辑问卷受众：视觉组"));
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    await screen.findByText("问卷修改已保存。");
    expect(csrfFetchMock).toHaveBeenCalledWith("/admin/intentions/survey-1", {
      method: "PATCH",
      body: expect.stringContaining(
        '"audience":{"all_students":false,"direction_ids":["direction-2"]}',
      ),
    });
  });

  it.each([
    "培训方向问卷",
    "意向选择问卷",
    "问卷意向选择",
  ])("hides first-choice direction assignment for another title: %s", (title) => {
    render(
      <IntentionAdminPanel
        directions={[direction()]}
        initialSurveys={[adminSurvey({ title })]}
      />,
    );

    expect(
      screen.queryByRole("button", { name: "配置第一志愿方向" }),
    ).not.toBeInTheDocument();
  });

  it("maps every first-choice option to an active direction and reports the result", async () => {
    apiFetchMock.mockResolvedValue(adminDetail({ title: "意向选择" }));
    csrfFetchMock.mockResolvedValue({
      survey_id: "survey-1",
      question_id: "question-first",
      eligible_response_count: 2,
      updated_count: 1,
      unchanged_count: 1,
      skipped_response_count: 1,
    });
    const confirmMock = vi
      .spyOn(window, "confirm")
      .mockReturnValue(true);
    render(
      <IntentionAdminPanel
        directions={[
          direction(),
          direction({
            id: "direction-2",
            code: "vision",
            name: "视觉组",
          }),
          direction({
            id: "direction-inactive",
            code: "inactive",
            name: "停用技术组",
            is_active: false,
          }),
        ]}
        initialSurveys={[adminSurvey({ title: "意向选择" })]}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "配置第一志愿方向" }),
    );

    expect(await screen.findByText("第一题：第一志愿")).toBeInTheDocument();
    expect(
      screen.queryByLabelText("电控对应技术方向"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("option", { name: "停用技术组" }),
    ).not.toBeInTheDocument();
    const applyButton = screen.getByRole("button", {
      name: "确认按第一志愿配置方向",
    });
    expect(applyButton).toBeDisabled();

    fireEvent.change(screen.getByLabelText("机器人对应技术方向"), {
      target: { value: "direction-1" },
    });
    fireEvent.change(screen.getByLabelText("视觉对应技术方向"), {
      target: { value: "direction-2" },
    });
    expect(applyButton).toBeEnabled();
    fireEvent.click(applyButton);

    await screen.findByText("已按当前最新第一志愿完成技术方向配置。");
    expect(confirmMock).toHaveBeenCalledWith(
      expect.stringContaining("不会重算已发布作业的固定受众"),
    );
    expect(apiFetchMock).toHaveBeenCalledWith(
      "/admin/intentions/survey-1",
    );
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/admin/intentions/survey-1/apply-first-choice-directions",
      {
        method: "POST",
        body: JSON.stringify({
          question_id: "question-first",
          option_mappings: [
            {
              option_id: "option-robot",
              direction_id: "direction-1",
            },
            {
              option_id: "option-vision",
              direction_id: "direction-2",
            },
          ],
          confirm_overwrite: true,
        }),
      },
    );
    const result = screen.getByLabelText("方向配置结果");
    expect(result).toHaveTextContent(/符合条件\s*2 人/);
    expect(result).toHaveTextContent(/实际更新\s*1 人/);
    expect(result).toHaveTextContent(/方向未变化\s*1 人/);
    expect(result).toHaveTextContent(/跳过回答\s*1 人/);
    confirmMock.mockRestore();
  });

  it("does not apply first-choice directions when overwrite confirmation is cancelled", async () => {
    apiFetchMock.mockResolvedValue(adminDetail({ title: "意向选择" }));
    const confirmMock = vi
      .spyOn(window, "confirm")
      .mockReturnValue(false);
    render(
      <IntentionAdminPanel
        directions={[
          direction(),
          direction({
            id: "direction-2",
            code: "vision",
            name: "视觉组",
          }),
        ]}
        initialSurveys={[adminSurvey({ title: "意向选择" })]}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "配置第一志愿方向" }),
    );
    await screen.findByText("第一题：第一志愿");
    fireEvent.change(screen.getByLabelText("机器人对应技术方向"), {
      target: { value: "direction-1" },
    });
    fireEvent.change(screen.getByLabelText("视觉对应技术方向"), {
      target: { value: "direction-2" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "确认按第一志愿配置方向" }),
    );

    expect(confirmMock).toHaveBeenCalledTimes(1);
    expect(csrfFetchMock).not.toHaveBeenCalled();
    confirmMock.mockRestore();
  });

  it("rejects a multiple-choice first question in the direction mapping UI", async () => {
    apiFetchMock.mockResolvedValue(
      adminDetail({
        title: "意向选择",
        questions: [
          {
            ...adminDetail().questions[0]!,
            allow_multiple: true,
          },
        ],
      }),
    );
    render(
      <IntentionAdminPanel
        directions={[direction()]}
        initialSurveys={[adminSurvey({ title: "意向选择" })]}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "配置第一志愿方向" }),
    );

    expect(
      await screen.findByText(
        "问卷第一题是多选题，无法据此配置唯一技术方向。",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "确认按第一志愿配置方向" }),
    ).not.toBeInTheDocument();
  });
});
