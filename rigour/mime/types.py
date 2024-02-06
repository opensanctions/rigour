from rigour.util import gettext

DEFAULT = "application/octet-stream"
DIRECTORY = "inode/directory"
EMPTY = "inode/x-empty"

PLAIN = "text/plain"
PDF = "application/pdf"
EXCEL = "application/vnd.ms-excel"
XLS = EXCEL
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
WORD = "application/vnd.ms-word"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessing"
CSV = "text/csv"
RTF = "text/rtf"
XML = "application/xml"
PSD = "image/vnd.adobe.photoshop"
RAR = "application/rar"
ZIP = "application/zip"
GZIP = "application/gzip"
RFC822 = "message/rfc822"
HTML = "text/html"
JPEG = "image/jpeg"
PNG = "image/png"
GIF = "image/gif"
TIFF = "image/tiff"
DJVU = "image/x.djvu"
OPF = "application/xml+opfmessage"
OUTLOOK = "application/vnd.ms-outlook"
ZIP = "application/zip"
JSON = "application/json"
FTM = "application/json+ftm"
FTM_RSLV = "application/json+ftm-rslv"
FTM_STMT = "application/json+ftm-statements"

MIXED = "multipart/mixed"
ALTERNATIVE = "multipart/alternative"
RELATED = "multipart/related"


LABELS = {
    DEFAULT: gettext("Unknown file type"),
    DIRECTORY: gettext("Directory"),
    EMPTY: gettext("Empty file"),
    PLAIN: gettext("Plain text"),
    PDF: gettext("Portable Document Format"),
    EXCEL: gettext("Microsoft Excel"),
    XLSX: gettext("Microsoft Excel 2002+"),
    WORD: gettext("Microsoft Word"),
    DOCX: gettext("Microsoft Word 2002+"),
    CSV: gettext("Comma-separated table"),
    RTF: gettext("Rich text"),
    PSD: gettext("Adobe Photoshop"),
    RAR: gettext("WinRAR archive"),
    ZIP: gettext("Zip archive"),
    GZIP: gettext("GZip archive"),
    RFC822: gettext("Plain E-Mail"),
    HTML: gettext("HTML Web Page"),
    JPEG: gettext("JPEG Image"),
    TIFF: gettext("Tagged Image File Format"),
    DJVU: gettext("DejaVu E-Book"),
    PNG: gettext("Portable Network Graphics"),
    GIF: gettext("Graphics Interchange Format"),
    OPF: gettext("Microsoft Outlook for Mac E-Mail"),
    OUTLOOK: gettext("Microsoft Outlook E-Mail"),
    JSON: gettext("JavaScript Object Notation"),
    XML: gettext("eXtensible Markup Language"),
    FTM: gettext("FollowTheMoney Entities"),
    FTM_RSLV: gettext("FollowTheMoney Integrated"),
    FTM_STMT: gettext("FollowTheMoney Statements"),
}
