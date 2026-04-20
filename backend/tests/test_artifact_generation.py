from app.services.artifact_generation import ArtifactGenerationService


def test_validate_html_rejects_empty_output() -> None:
    service = ArtifactGenerationService()

    try:
        service.validate_html_output("页面方案", "   ")
    except ValueError as exc:
        assert "HTML 不能为空" in str(exc)
    else:
        raise AssertionError("Expected empty HTML to be rejected")


def test_validate_html_rejects_missing_title_and_external_script() -> None:
    service = ArtifactGenerationService()

    bad_html = """
    <!doctype html>
    <html lang="zh-CN">
      <head>
        <meta charset="UTF-8" />
        <script src="https://cdn.example.com/app.js"></script>
      </head>
      <body>
        <main><h1>页面方案</h1></main>
      </body>
    </html>
    """

    try:
        service.validate_html_output("页面方案", bad_html)
    except ValueError as exc:
        message = str(exc)
        assert "title" in message or "外链脚本" in message
    else:
        raise AssertionError("Expected invalid HTML to be rejected")


def test_validate_html_accepts_complete_local_document() -> None:
    service = ArtifactGenerationService()

    html = """
    <!doctype html>
    <html lang="zh-CN">
      <head>
        <meta charset="UTF-8" />
        <title>页面方案</title>
      </head>
      <body>
        <main>
          <h1>页面方案</h1>
          <section>总览</section>
        </main>
      </body>
    </html>
    """

    assert service.validate_html_output("页面方案", html) == html.strip()
