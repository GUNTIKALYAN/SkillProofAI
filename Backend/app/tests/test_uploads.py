from io import BytesIO

from docx import Document
from fastapi.testclient import TestClient

from app.conftest import register
from app.main import app

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _docx(paragraphs: list[str]) -> bytes:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _headers(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {register(client)}"}


def test_rejects_non_resume_extension() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/parse-resume",
            headers=_headers(client),
            files={"resume": ("notes.txt", b"python", "text/plain")},
        )
    assert response.status_code == 400
    assert "PDF or DOCX" in response.json()["detail"]


def test_rejects_mismatched_file_content() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/parse-resume",
            headers=_headers(client),
            files={"resume": ("resume.pdf", b"not a pdf", "application/pdf")},
        )
    assert response.status_code == 400
    assert "does not match" in response.json()["detail"]


def test_rejects_empty_resume() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/parse-resume",
            headers=_headers(client),
            files={"resume": ("resume.pdf", b"", "application/pdf")},
        )
    assert response.status_code == 400
    assert response.json()["detail"] == "Resume file is empty"


def test_rejects_resume_over_size_limit() -> None:
    payload = b"%PDF" + (b"a" * (5 * 1024 * 1024))
    with TestClient(app) as client:
        response = client.post(
            "/api/parse-resume",
            headers=_headers(client),
            files={"resume": ("resume.pdf", payload, "application/pdf")},
        )
    assert response.status_code == 413
    assert "5 MB" in response.json()["detail"]


def test_unreadable_pdf_is_a_client_error() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/parse-resume",
            headers=_headers(client),
            files={"resume": ("resume.pdf", b"%PDF-1.4\nnot a pdf", "application/pdf")},
        )
    assert response.status_code == 400
    assert response.json()["detail"] == "Could not read the resume file"


def test_docx_with_no_text_is_a_client_error() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/parse-resume",
            headers=_headers(client),
            files={"resume": ("resume.docx", _docx([]), DOCX_TYPE)},
        )
    assert response.status_code == 400
    assert response.json()["detail"] == "No text extracted from DOCX"


def test_removed_nollm_route_is_gone() -> None:
    with TestClient(app) as client:
        response = client.post("/api/analyze_nollm")
    assert response.status_code == 404
