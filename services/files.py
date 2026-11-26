import os
import uuid

from werkzeug.utils import secure_filename

try:
    from pypdf import PdfReader
except ImportError:  # pypdf is optional; without it PDFs get no page count
    PdfReader = None


ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def _file_size(stream):
    """Return the number of bytes in a file stream without reading it all."""
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    return size


def _count_pdf_pages(path):
    """Return the page count of a PDF, or None if pypdf is not installed."""
    if PdfReader is None:
        return None
    reader = PdfReader(path)
    return len(reader.pages)


def validate_and_save(file_storage, upload_dir):
    """Check an uploaded file and save it with a random UUID filename.

    Returns a dict with original_filename, stored_path, size_bytes, and
    detected_page_count (None for Word files or when pypdf is missing).
    Raises ValueError if the file is not allowed, too large, or empty.
    """
    original_name = secure_filename(file_storage.filename or "")
    if not original_name:
        raise ValueError("File has no name")

    ext = os.path.splitext(original_name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Only .pdf, .doc, and .docx files are allowed")

    size = _file_size(file_storage.stream)
    if size == 0:
        raise ValueError("File is empty")
    if size > MAX_UPLOAD_BYTES:
        raise ValueError("File is larger than 10 MB")

    os.makedirs(upload_dir, exist_ok=True)
    # The stored name is random, so users cannot guess or overwrite other files
    stored_path = os.path.join(upload_dir, uuid.uuid4().hex + ext)
    file_storage.save(stored_path)

    page_count = None
    if ext == ".pdf":
        try:
            page_count = _count_pdf_pages(stored_path)
        except Exception:
            # Unreadable PDF: remove the saved copy and reject it
            os.remove(stored_path)
            raise ValueError("Could not read this PDF")

    return {
        "original_filename": original_name,
        "stored_path": stored_path,
        "size_bytes": size,
        "detected_page_count": page_count,
    }
