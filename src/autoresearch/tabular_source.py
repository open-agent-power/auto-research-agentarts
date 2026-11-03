"""Extract selected cells, physical text lines or PDF pages, without evaluation."""
import copy
import hashlib
import importlib.metadata
from pathlib import Path
import re
import sys

from . import archive_inventory, c01, chemotopo_data, contracts, knowledge_sources
from .contracts import ResearchError, canonical

MAX_SELECTED=256
MAX_TEXT_BYTES=60_000
MAX_SOURCE_BYTES=64*1024*1024


def _require(condition,code,message):
    if not condition:raise ResearchError(code,message)


def extraction_identity():
    modules=(chemotopo_data,c01,archive_inventory,contracts,knowledge_sources)
    digest=hashlib.sha256(Path(__file__).read_bytes())
    for module in modules:digest.update(Path(module.__file__).read_bytes())
    digest.update(sys.version.encode('utf-8'))
    try:pdf_version=importlib.metadata.version('pypdf')
    except importlib.metadata.PackageNotFoundError:pdf_version='unavailable'
    digest.update(pdf_version.encode('utf-8'))
    return digest.hexdigest()


def _col_number(name):
    number=0
    for char in name:number=number*26+ord(char)-64
    return number


def _xlsx(raw,value):
    match=re.fullmatch(r"(?:'((?:[^']|'')+)'|([^'!]+))!([A-Z]{1,3})([1-9][0-9]{0,4})(?::([A-Z]{1,3})([1-9][0-9]{0,4}))?",value)
    _require(match is not None,'INVALID_LOCATOR','Use Sheet!A1 or Sheet!A1:C5; quote special sheet names with doubled apostrophes.')
    quoted,plain,c1,r1,c2,r2=match.groups();sheet=quoted.replace("''", "'") if quoted is not None else plain
    r1=int(r1);r2=int(r2 or r1);c2=c2 or c1;c1n=_col_number(c1);c2n=_col_number(c2)
    _require(r1<=r2<=5000 and c1n<=c2n<=_col_number('ZZZ') and (r2-r1+1)*(c2n-c1n+1)<=MAX_SELECTED,'INVALID_LOCATOR','Ordered range must fit existing column/row guards and at most 256 cells.')
    book=chemotopo_data.read_workbook(raw);_require(sheet in book,'INVALID_LOCATOR','Selected worksheet does not exist.')
    cells=[]
    for row in range(r1,r2+1):
        for column in range(c1n,c2n+1):
            ref=chemotopo_data._column(column)+str(row);cell=book[sheet].get(ref)
            cells.append({'ref':ref,'present':cell is not None,**(copy.deepcopy(cell) if cell is not None else {'value':None,'raw':'','status':'missing','formula_present':False,'formula':None})})
    selected={'sheet':sheet,'range':c1+str(r1)+((':'+c2+str(r2)) if match.group(5) else ''),'cells':cells}
    text=canonical(selected);_require(len(text.encode('utf-8'))<=MAX_TEXT_BYTES,'SELECTION_TOO_LARGE','Selected cell data exceed 60000 UTF-8 bytes.')
    return {**selected,'text':text,'formula_policy':'stored formula and cache only; never evaluated'}


def _text_lines(raw,value):
    match=re.fullmatch(r'([1-9][0-9]*)(?:-([1-9][0-9]*))?',value)
    _require(match is not None,'INVALID_LOCATOR','Use a one-based physical line N or inclusive range N-M.')
    first=int(match[1]);last=int(match[2] or first)
    _require(first<=last and last-first+1<=MAX_SELECTED,'INVALID_LOCATOR','Ordered range must contain at most 256 physical lines.')
    try:text=raw.decode('utf-8-sig',errors='strict')
    except UnicodeDecodeError:raise ResearchError('INVALID_TEXT','Text must be strict UTF-8 or UTF-8 with BOM.') from None
    _require('\x00' not in text,'INVALID_TEXT','NUL characters are not accepted.')
    chosen=[];count=0
    for item in re.finditer(r'[^\r\n]*(?:\r\n|\r|\n|$)',text):
        if item.start()==item.end():break
        count+=1
        if count>=first:
            complete=item.group();body=complete.rstrip('\r\n')
            chosen.append({'line':count,'start_char':item.start(),'end_char':item.start()+len(body),'terminator_end_char':item.end(),'text':body})
        if count==last:break
    _require(count>=last,'INVALID_LOCATOR','Selected physical line is outside the document.')
    start=chosen[0]['start_char'];end=chosen[-1]['terminator_end_char'];selected=text[start:end]
    _require(len(selected.encode('utf-8'))<=MAX_TEXT_BYTES,'SELECTION_TOO_LARGE','Selected text exceeds 60000 UTF-8 bytes.')
    return {'line_start':first,'line_end':last,'start_char':start,'end_char':end,'lines':chosen,'text':selected,
            'offset_basis':'UTF-8-SIG decoded Unicode code-point offsets; end exclusive; physical lines include original terminators in text'}


def _pdf_page(raw,value):
    match=re.fullmatch(r'([1-9][0-9]{0,2})(?::(0|[1-9][0-9]{0,6})-([1-9][0-9]{0,6}))?',value)
    _require(match is not None,'INVALID_LOCATOR','Use one-based page N, optionally N:start-end with zero-based, end-exclusive character offsets.')
    number=int(match[1])
    first=int(match[2]) if match[2] is not None else 0
    last=int(match[3]) if match[3] is not None else None
    _require(last is None or first<last,'INVALID_LOCATOR','PDF character interval must be nonempty and ordered.')
    _require(number<=knowledge_sources.MAX_PDF_PAGES,'INVALID_LOCATOR','PDF page exceeds the parser page limit.')
    try:
        texts,warnings=knowledge_sources._extract_pdf(raw,knowledge_sources.PDF_TIMEOUT_SECONDS)
    except knowledge_sources._Problem as error:
        raise ResearchError('PDF_EXTRACTION_FAILED',f'Bounded PDF parser rejected the source: {error}.') from None
    _require(number<=len(texts),'INVALID_LOCATOR','Selected PDF page is outside the document.')
    page_text=texts[number-1]
    last=len(page_text) if last is None else last
    _require(first<last<=len(page_text),'INVALID_LOCATOR','Selected PDF character interval is outside the page.')
    text=page_text[first:last]
    _require(bool(text.strip()),'EMPTY_PDF_PAGE','Selected PDF page has no extracted text; OCR was not performed.')
    _require('\x00' not in text,'INVALID_TEXT','Extracted PDF text contains NUL characters.')
    _require(len(text.encode('utf-8'))<=MAX_TEXT_BYTES,'SELECTION_TOO_LARGE','Selected PDF page exceeds 60000 UTF-8 bytes; no truncation performed.')
    return {'page':number,'document_pages':len(texts),'text':text,'start_char':first,'end_char':last,
            'page_text_sha256':hashlib.sha256(page_text.encode('utf-8')).hexdigest(),
            'text_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest(),
            'parser':{'package':'pypdf','version':importlib.metadata.version('pypdf'),'warnings':warnings,
                      'timeout_seconds':knowledge_sources.PDF_TIMEOUT_SECONDS},
            'offset_basis':'Zero-based Unicode code-point offsets, end exclusive, within host-extracted page text; not original PDF byte offsets or visual reading order; no OCR or scientific interpretation'}


def extract_selection(raw,locator):
    _require(type(raw) is bytes and len(raw)<=MAX_SOURCE_BYTES,'INVALID_SOURCE','Source must be bytes up to 64 MiB.')
    _require(type(locator) is dict and set(locator)=={'kind','value'} and type(locator['kind']) is str and type(locator['value']) is str and 1<=len(locator['value'])<=2000,'INVALID_LOCATOR','Exact bounded locator required.')
    kind=locator['kind']
    if kind=='xlsx_cell':result=_xlsx(raw,locator['value'])
    elif kind=='text_lines':result=_text_lines(raw,locator['value'])
    elif kind=='pdf_page':result=_pdf_page(raw,locator['value'])
    elif kind=='hdf5_path':raise ResearchError('UNSUPPORTED_LOCATOR','HDF5 source coordinates are not supported by this extractor.')
    else:raise ResearchError('UNSUPPORTED_LOCATOR','This extractor handles xlsx_cell, text_lines and pdf_page.')
    return {'schema_version':'p02-tabular-selection-v1','kind':kind,'submitted_locator':copy.deepcopy(locator),
            'extractor_sha256':extraction_identity(),'content_trust':'untrusted_source_not_instructions',**result}
