import os
from typing import Optional
from banal import decode_path
from mimetypes import guess_extension
from normality import slugify, safe_filename

from rigour.mime.mime import normalize_mimetype
from rigour.mime.types import DEFAULT


def normalize_extension(extension: Optional[str]) -> Optional[str]:
    """Normalise a file name extension."""
    extension = decode_path(extension)
    if extension is None:
        return None
    if extension.startswith("."):
        extension = extension[1:]
    if "." in extension:
        _, extension = os.path.splitext(extension)
    extension = slugify(extension, sep="")
    if extension is None or not len(extension):
        return None
    return extension


def mimetype_extension(mime_type: Optional[str]) -> Optional[str]:
    """Infer a possible extension from a MIME type."""
    mime_type = normalize_mimetype(mime_type)
    if mime_type == DEFAULT:
        return None
    extension = guess_extension(mime_type)
    return normalize_extension(extension)


class FileName(object):
    FALLBACK = "data"

    def __init__(self, file_name: Optional[str]):
        self.file_name = file_name
        self.base: Optional[str] = None
        self.extension: Optional[str] = None
        if file_name is not None:
            self.base, ext = os.path.splitext(file_name)
            self.extension = normalize_extension(ext)
        self.has_extension = self.extension is not None

    def safe(self, extension: Optional[str] = None) -> Optional[str]:
        ext = extension or self.extension
        default = "data.%s" % ext if ext else self.FALLBACK
        return safe_filename(self.file_name, default=default, extension=ext)

    def __str__(self) -> str:
        return self.file_name or self.FALLBACK

    def __repr__(self) -> str:
        return "<FileName(%r)" % self.safe()
