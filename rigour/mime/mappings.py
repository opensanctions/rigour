from typing import Dict

from rigour.mime.types import DEFAULT, PLAIN, DIRECTORY
from rigour.mime.types import EXCEL, PDF, CSV, RTF, PSD, WORD, XML
from rigour.mime.types import RAR, ZIP, GZIP, TIFF, JPEG

REPLACE: Dict[str, str] = {
    "x-unknown/unknown": DEFAULT,
    "unknown/unknown": DEFAULT,
    "x-unknown/octet-stream": DEFAULT,
    "application/x-unknown": DEFAULT,
    "file/unknown": DEFAULT,
    "content/unknown": DEFAULT,
    "application/x-unknown-application-octet-stream": DEFAULT,
    "x-unknown/stream": DEFAULT,
    "application/binary": DEFAULT,
    # Invalid
    "image/*": DEFAULT,
    "*/*": DEFAULT,
    # CSV
    "application/csv": CSV,
    # XML
    "text/xml": XML,
    # Plain
    "plain/text": PLAIN,
    "text/text": PLAIN,
    # Rich text
    "application/rtf": RTF,
    "file/rtf": RTF,
    "text/richtext": RTF,
    "text/enriched": RTF,
    # Word
    "application/x-msword": WORD,
    "application/msword": WORD,
    "application/vnd.ms-word.document.macroenabled.12": "application/vnd.ms-word.document.12",  # noqa
    # Excel normalisations:
    "application/x-excel": EXCEL,
    "application/x-msexcel": EXCEL,
    "application/excel": EXCEL,
    "application/x-ms-excel": EXCEL,
    "application/x-unknown-application-vnd.ms-excel": EXCEL,
    "application/vnd.ms-excel.12": EXCEL,
    # PDF
    "image/pdf": PDF,
    "application/x-pdf": PDF,
    "document/pdf": PDF,
    "x-application/apple-pdf": PDF,
    "file/pdf": PDF,
    "application/x-unknown-application-pdf": PDF,
    "text/pdf": PDF,
    "invalid/pdf": PDF,
    "application/vnd.pdf": PDF,
    "x-unknown/pdf": PDF,
    # RAR
    "application/x-rar": RAR,
    "application/x-rar-compressed": RAR,
    # Zip
    "application/x-zip": ZIP,
    "application/x-zip-compressed": ZIP,
    "appliation/zip": ZIP,
    # GZip
    "application/x-gzip": GZIP,
    "application/x-gzip-compressed": GZIP,
    "application/x-gunzip": GZIP,
    # JPEG
    "image/x-citrix-jpeg": JPEG,
    "application/jpeg": JPEG,
    "image/jpg": JPEG,
    "application/jpg": JPEG,
    # PSD
    "image/x-photoshop": PSD,
    "application/x-photoshop": PSD,
    "image/psd": PSD,
    # Tiff
    "image/x-tiff": TIFF,
    "application/tiff": TIFF,
    "application/x-tiff": TIFF,
    "text/x-vcard": "text/vcard",
    "text/directory": DIRECTORY,
    "application/x-msi": "application/vnd.ms-msi",
    "image/x.djvu": "image/vnd.djvu",
    "application/html": "text/html",
}
