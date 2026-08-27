import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { IntentionAdminPanel } from "@/components/admin/intention-admin-panel";
import { IntentionForm } from "@/components/intentions/intention-form";
import type {
  AdminIntentionSurvey,
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
    title: "培训方向意向",
    description_html: "<p>请选择培训方向</p>",
    status: "open",
    allow_multiple: false,
    starts_at: null,
    ends_at: null,
    option_count: 2,
    has_response: false,
    options: [
      { id: "option-robot", label: "机器人", display_order: 0 },
      { id: "option-vision", label: "视觉", display_order: 1 },
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
    title: "培训方向意向",
    description_markdown: "请选择",
    status: "draft",
    allow_multiple: false,
    starts_at: null,
    ends_at: null,
    option_count: 2,
    responded_count: 0,
    created_at: "2026-08-27T00:00:00Z",
    updated_at: "2026-08-27T00:00:00Z",
    revision: 1,
    ...overrides,
  };
}

describe("student intention form", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    csrfFetchMock.mockReset();
    qrToDataUrlMock.mockReset();
    refreshMock.mockReset();
  });

  it("submits exactly one option for a single-choice survey", async () => {
    csrfFetchMock.mockResolvedValue({});
    render(<IntentionForm initialSurvey={intention()} />);

    fireEvent.click(screen.getByLabelText("机器人"));
    fireEvent.click(screen.getByLabelText("视觉"));
    fireEvent.change(screen.getByLabelText("补充说明（可选）"), {
      target: { value: "  希望参与视觉组  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交我的意向" }));

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledTimes(1));
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/intentions/survey-1/response",
      {
        method: "PUT",
        body: JSON.stringify({
          selected_option_ids: ["option-vision"],
          free_text: "希望参与视觉组",
        }),
      },
    );
    expect(screen.getByText(/可以在调查关闭前继续修改/)).toBeInTheDocument();
  });

  it("loads and updates an existing multiple-choice response", async () => {
    csrfFetchMock.mockResolvedValue({});
    render(
      <IntentionForm
        initialSurvey={
          intention({
            allow_multiple: true,
            has_response: true,
            response: {
              selected_option_ids: ["option-robot"],
              free_text: null,
              submitted_at: "2026-08-27T01:00:00Z",
            },
          })
        }
      />,
    );

    expect(screen.getByLabelText("机器人")).toBeChecked();
    fireEvent.click(screen.getByLabelText("视觉"));
    fireEvent.click(screen.getByRole("button", { name: "更新我的意向" }));

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledTimes(1));
    expect(JSON.parse(String(csrfFetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      selected_option_ids: ["option-robot", "option-vision"],
      free_text: null,
    });
  });
});

describe("administrator intention panel", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    csrfFetchMock.mockReset();
    qrToDataUrlMock.mockReset();
    refreshMock.mockReset();
  });

  it("creates a multiple-choice survey from one option per line", async () => {
    csrfFetchMock.mockResolvedValue(
      adminSurvey({ id: "survey-created", allow_multiple: true }),
    );
    render(<IntentionAdminPanel initialSurveys={[]} />);

    fireEvent.change(screen.getByLabelText("标题"), {
      target: { value: "  组队岗位意向  " },
    });
    fireEvent.change(screen.getByLabelText("选项（每行一个）"), {
      target: { value: "队长\n机械\n视觉" },
    });
    fireEvent.click(screen.getByLabelText("允许学生多选"));
    fireEvent.click(screen.getByRole("button", { name: "创建调查" }));

    await screen.findByText("调查已创建。开放填写后学生即可提交意向。");
    expect(csrfFetchMock).toHaveBeenCalledWith("/admin/intentions", {
      method: "POST",
      body: JSON.stringify({
        title: "组队岗位意向",
        description_markdown: "",
        options: [{ label: "队长" }, { label: "机械" }, { label: "视觉" }],
        allow_multiple: true,
      }),
    });
  });

  it("opens a survey, generates a local QR code, and then closes it", async () => {
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
    await screen.findByText("调查状态已更新为“开放中”。");
    fireEvent.click(screen.getByRole("button", { name: "生成二维码" }));

    await screen.findByAltText("培训方向意向移动端填写二维码");
    expect(qrToDataUrlMock).toHaveBeenCalledWith(
      "https://training.invalid/intentions/survey-1?token=qr-token",
      expect.objectContaining({ width: 280 }),
    );
    fireEvent.click(screen.getByRole("button", { name: "关闭调查" }));
    await screen.findByText("调查状态已更新为“已关闭”。");
    expect(screen.queryByRole("button", { name: "生成二维码" })).not.toBeInTheDocument();
  });

  it("shows aggregate counts and percentages without individual responses", async () => {
    apiFetchMock.mockResolvedValue({
      survey_id: "survey-1",
      total_active_students: 8,
      responded_count: 2,
      response_rate: 25,
      options: [
        {
          option_id: "option-robot",
          label: "机器人",
          response_count: 1,
          percentage: 50,
        },
      ],
    });
    render(
      <IntentionAdminPanel initialSurveys={[adminSurvey({ status: "open" })]} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "查看统计" }));

    expect(await screen.findByText(/填写率 25%/)).toBeInTheDocument();
    expect(screen.getByText("1 · 50%")).toBeInTheDocument();
    expect(
      screen.getByRole("progressbar", { name: "机器人选择比例" }),
    ).toHaveAttribute("aria-valuenow", "50");
    expect(screen.queryByText(/学生姓名|学号/)).not.toBeInTheDocument();
  });
});
