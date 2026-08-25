from app.core.markdown import render_markdown


def test_render_markdown_supports_safe_content_and_demotes_headings() -> None:
    rendered = render_markdown(
        "# 通知\n\n**重要** [资料](https://example.invalid/docs)\n\n"
        "| 项目 | 状态 |\n| --- | --- |\n| 电控 | 完成 |\n\n```python\nprint('<safe>')\n```"
    )

    assert "<h2>通知</h2>" in rendered
    assert "<strong>重要</strong>" in rendered
    assert 'href="https://example.invalid/docs"' in rendered
    assert 'rel="noopener noreferrer nofollow"' in rendered
    assert "<table>" in rendered
    assert "&lt;safe&gt;" in rendered


def test_render_markdown_removes_raw_html_remote_images_and_dangerous_urls() -> None:
    rendered = render_markdown(
        "<script>alert(1)</script>\n\n"
        '<iframe src="https://example.invalid"></iframe>\n\n'
        "[危险](javascript:alert(1))\n\n"
        "![跟踪](https://tracker.invalid/pixel.png)\n\n"
        '<a href="https://example.invalid" onclick="alert(1)">链接</a>'
    )

    assert "<script" not in rendered
    assert "<iframe" not in rendered
    assert 'href="javascript:' not in rendered
    assert "<img" not in rendered
    assert '<a href="https://example.invalid"' not in rendered
    assert "tracker.invalid" not in rendered


def test_render_markdown_escapes_raw_html_instead_of_executing_it() -> None:
    rendered = render_markdown("普通文本 <object data='x'>不可执行</object>")

    assert "<object" not in rendered
    assert "&lt;object" in rendered
