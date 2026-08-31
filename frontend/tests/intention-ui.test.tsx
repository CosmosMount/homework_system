import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
      }),
    });
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

  it("sends email to one active technical direction", async () => {
    csrfFetchMock.mockResolvedValue({
      survey_id: "survey-1",
      requested_count: 3,
      queued_count: 3,
      already_queued_count: 0,
    });
    render(
      <IntentionAdminPanel
        directions={[
          direction(),
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
      screen.queryByRole("option", { name: "停用技术组" }),
    ).not.toBeInTheDocument();
    const sendButton = screen.getByRole("button", {
      name: "向该技术组发送邮件",
    });
    expect(sendButton).toBeDisabled();

    fireEvent.change(screen.getByLabelText("选择技术组"), {
      target: { value: "direction-1" },
    });
    fireEvent.click(sendButton);

    await screen.findByText("已为 3 名成员创建邮件任务。");
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/admin/intentions/survey-1/email-notifications",
      {
        method: "POST",
        headers: { "Idempotency-Key": expect.any(String) },
        body: JSON.stringify({
          recipient_scope: "direction",
          direction_id: "direction-1",
        }),
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

  it("loads and displays complete content for a non-draft questionnaire", async () => {
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
      screen.getByText(/已开放、关闭或归档的问卷只能查看/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "编辑问卷" }),
    ).not.toBeInTheDocument();
  });

  it("edits a draft questionnaire and refreshes its visible content", async () => {
    const draftDetail = adminDetail();
    const updated = adminDetail({
      title: "更新后的培训方向问卷",
      description_markdown: "更新说明",
      max_submissions: 3,
      revision: 2,
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
    render(<IntentionAdminPanel initialSurveys={[adminSurvey()]} />);

    fireEvent.click(screen.getByRole("button", { name: "编辑问卷" }));
    const titleInput = await screen.findByLabelText("编辑问卷标题");
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
        starts_at: null,
        ends_at: null,
      }),
    });
    expect(screen.getByText("1. 首选方向（单选）")).toBeInTheDocument();
    expect(screen.getByText("机械")).toBeInTheDocument();
  });
});
