#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF 转 Word 单文件工具（含水印清除修复版）
================================================

一个文件搞定：智能分流（扫描页保图 / 电子页可编辑）+ 自动识别并清除水印
（图片水印 + 文字水印），并在文末附《水印标注清单》。

【安装依赖（只需一次）】
    pip install pymupdf python-docx pdf2docx pillow

【基本用法】
    python pdf2word.py 你的文件.pdf
        → 生成「你的文件.docx」，默认自动清除检测到的高置信度水印。

    python pdf2word.py 你的文件.pdf -o 结果.docx     # 指定输出名
    python pdf2word.py 你的文件.pdf --keep-watermarks # 只标注、不删除水印
    python pdf2word.py 你的文件.pdf --password 1234   # 加密PDF
    python pdf2word.py 你的文件.pdf --force-image      # 强制整页保图
    python pdf2word.py 你的文件.pdf --dpi 300          # 保图分辨率
    python pdf2word.py 你的文件.pdf --analyze          # 只分析不转换

说明：水印若与正文高度重叠、或烧进扫描图里，无法在不损伤正文的前提下单独删除，
这类只会在清单中标注提示，需人工处理。
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger("pdf2word")


# ======================================================================
# 依赖检查（给非技术用户友好的提示）
# ======================================================================
def _require_deps():
    """只强制要求核心依赖（pymupdf + python-docx）。pdf2docx 为可选。"""
    missing = []
    errs = []
    for mod, pipname in [("pymupdf", "pymupdf"), ("docx", "python-docx")]:
        try:
            __import__(mod)
        except Exception as e:
            missing.append(pipname)
            errs.append(f"{pipname}: {e!r}")
    if missing:
        print("缺少必要依赖：", ", ".join(missing))
        for e in errs:
            print("  ", e)
        print("请先运行： pip install pymupdf python-docx pdf2docx pillow")
        sys.exit(1)


# pdf2docx 是可选组件：用于「可编辑还原」。若无法加载则自动降级为整页保图。
_PDF2DOCX_CONV = None
_PDF2DOCX_ERR = None


def _try_import_pdf2docx():
    global _PDF2DOCX_CONV, _PDF2DOCX_ERR
    if _PDF2DOCX_CONV is not None or _PDF2DOCX_ERR is not None:
        return _PDF2DOCX_CONV, _PDF2DOCX_ERR
    try:
        from pdf2docx import Converter as _Conv
        _PDF2DOCX_CONV = _Conv
    except Exception as e:
        _PDF2DOCX_ERR = e
    return _PDF2DOCX_CONV, _PDF2DOCX_ERR


# ======================================================================
# 1) 页面类型分析
# ======================================================================
class PageType(Enum):
    IMAGE = "image"
    ELECTRONIC = "electronic"
    MIXED = "mixed"


@dataclass
class PageAnalysis:
    page_index: int
    page_type: PageType
    width: float
    height: float
    text_chars: int = 0
    image_cov: float = 0.0
    text_cov: float = 0.0


@dataclass
class DocumentAnalysis:
    page_count: int
    pages: List[PageAnalysis]


def analyze_document(pdf_path: str, password: Optional[str] = None) -> DocumentAnalysis:
    import pymupdf
    doc = pymupdf.open(pdf_path)
    try:
        if doc.is_encrypted:
            if not password or not doc.authenticate(password):
                raise ValueError("PDF 已加密或密码错误")
        pages: List[PageAnalysis] = []
        for i, page in enumerate(doc):
            area = max(page.rect.width * page.rect.height, 1.0)
            chars = 0
            text_area = 0.0
            image_area = 0.0
            try:
                blocks = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_IMAGES)["blocks"]
            except Exception:
                blocks = []
            for b in blocks:
                a = bb_area(b.get("bbox", (0, 0, 0, 0)))
                if b.get("type") == 0:
                    text_area += a
                    for line in b.get("lines", []):
                        for s in line.get("spans", []):
                            chars += len(s.get("text", ""))
                elif b.get("type") == 1:
                    image_area += a
            text_cov = min(text_area / area, 1.0)
            image_cov = min(image_area / area, 1.0)
            has_draw = False
            try:
                has_draw = len(page.get_drawings()) > 50
            except Exception:
                pass

            if chars < 30:
                pt = PageType.IMAGE
            elif text_cov < 0.05 and image_cov > 0.4:
                pt = PageType.IMAGE
            elif chars >= 30 and (image_cov > 0.25 or has_draw):
                pt = PageType.MIXED
            else:
                pt = PageType.ELECTRONIC

            pages.append(PageAnalysis(
                page_index=i, page_type=pt,
                width=page.rect.width, height=page.rect.height,
                text_chars=chars, image_cov=round(image_cov, 4), text_cov=round(text_cov, 4),
            ))
        return DocumentAnalysis(page_count=len(doc), pages=pages)
    finally:
        doc.close()


def bb_area(bbox) -> float:
    return max((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]), 0.0)


# ======================================================================
# 2) 水印 / Logo 检测
# ======================================================================
@dataclass
class WatermarkCandidate:
    page_index: int
    kind: str  # text_watermark | image_logo | large_image_watermark
    content: str
    bbox: Tuple[float, float, float, float]
    confidence: float = 0.5
    notes: str = ""
    xref: Optional[int] = None


@dataclass
class WatermarkReport:
    candidates: List[WatermarkCandidate] = field(default_factory=list)
    high_confidence: List[WatermarkCandidate] = field(default_factory=list)


STRONG_KEYWORDS = [
    "水印", "样本", "样张", "绝密", "机密", "草稿", "内部资料",
    "draft", "sample", "confidential", "watermark", "preview",
    "禁止复制", "仅供参考", "内部使用", "测试版", "试用版",
]
WEAK_WORDS = {"内部", "保密", "管理", "药事", "药品", "规定", "办法"}

TEXT_WM_BRIGHTNESS = 170
TEXT_WM_MIN_SIZE = 14


def _judge_text_wm(span: dict, page_rect) -> Tuple[bool, float, str]:
    text = (span.get("text") or "").strip()
    if not text or len(text) < 2:
        return False, 0.0, ""
    size = span.get("size", 12)
    color = span.get("color", 0)
    bbox = span.get("bbox", (0, 0, 0, 0))
    r = (color >> 16) & 0xFF
    g = (color >> 8) & 0xFF
    b = color & 0xFF
    brightness = (r + g + b) / 3.0
    score = 0.0
    reasons = []
    if brightness > 200 and size >= 16:
        score += 0.45; reasons.append("极浅色+较大字")
    elif brightness > 180 and size >= 14:
        score += 0.25; reasons.append("浅色")
    lower = text.lower()
    for kw in STRONG_KEYWORDS:
        if kw in lower or kw in text:
            score += 0.55; reasons.append(f"强关键词:{kw}"); break
    if any(w in text for w in WEAK_WORDS) and score < 0.3:
        return False, 0.0, ""
    cx = (bbox[0] + bbox[2]) / 2
    cy = (bbox[1] + bbox[3]) / 2
    if (0.25 * page_rect.width < cx < 0.75 * page_rect.width) and \
       (0.3 * page_rect.height < cy < 0.7 * page_rect.height) and size >= 18:
        score += 0.2; reasons.append("页面中部大字")
    if len(text) <= 6 and score < 0.6:
        return False, 0.0, ""
    return score >= 0.55, min(score, 1.0), "; ".join(reasons)


def detect_watermarks(pdf_path: str, password: Optional[str] = None) -> WatermarkReport:
    import pymupdf
    doc = pymupdf.open(pdf_path)
    try:
        if doc.is_encrypted and password:
            doc.authenticate(password)

        cands: List[WatermarkCandidate] = []

        # 文字水印
        for pi, page in enumerate(doc):
            try:
                blocks = page.get_text("dict")["blocks"]
            except Exception:
                continue
            for b in blocks:
                if b.get("type") != 0:
                    continue
                for line in b.get("lines", []):
                    for s in line.get("spans", []):
                        is_wm, conf, reason = _judge_text_wm(s, page.rect)
                        if is_wm:
                            cands.append(WatermarkCandidate(
                                page_index=pi, kind="text_watermark",
                                content=(s.get("text") or "").strip()[:80],
                                bbox=tuple(s.get("bbox", (0, 0, 0, 0))),
                                confidence=conf, notes=reason,
                            ))

        # 图片水印 / Logo —— 关键规则：按「图片内容」跨页判重复（不看 xref！
        # 很多水印每页都重新嵌入、xref 各不相同，只有比内容才认得出）。
        # 同一张图在很多页重复出现 = Logo/水印（任何颜色都适用）；
        # 只出现一两次的图（哪怕很大）一律视为正文内容，绝不误删。
        import hashlib
        total_pages = max(len(doc), 1)
        rep_threshold = max(3, int(total_pages * 0.3))  # 至少在 30% 的页(或3页)重复
        by_hash: Dict[str, List[tuple]] = defaultdict(list)
        for pi, page in enumerate(doc):
            pw, ph = page.rect.width, page.rect.height
            parea = pw * ph + 1e-6
            try:
                images = page.get_images(full=True)
            except Exception:
                images = []
            for img in images:
                xref = img[0]
                try:
                    ib = doc.extract_image(xref)
                    h = hashlib.md5(ib["image"]).hexdigest()
                except Exception:
                    continue
                try:
                    rects = page.get_image_rects(xref)
                except Exception:
                    rects = []
                for rect in rects:
                    x0, y0, x1, y1 = rect
                    w, hh = x1 - x0, y1 - y0
                    ratio = (w * hh) / parea
                    is_corner = (
                        (x0 < pw * 0.28 and y0 < ph * 0.18) or
                        (x1 > pw * 0.72 and y0 < ph * 0.18) or
                        (x0 < pw * 0.28 and y1 > ph * 0.82) or
                        (x1 > pw * 0.72 and y1 > ph * 0.82)
                    )
                    is_header = y0 < ph * 0.12
                    by_hash[h].append((pi, xref, (x0, y0, x1, y1), ratio, is_corner, is_header))

        for h, occ in by_hash.items():
            pages_with = {o[0] for o in occ}
            n = len(pages_with)
            if n < rep_threshold:
                continue  # 内容不在多页重复 → 判为正文内容，跳过（不删）
            avg_ratio = sum(o[3] for o in occ) / len(occ)
            if avg_ratio < 0.005:
                continue  # 0 尺寸 / 不可见图，跳过
            corner_ratio = sum(1 for o in occ if o[4] or o[5]) / len(occ)
            for pi, xref, bbox, ratio, is_corner, is_header in occ:
                if avg_ratio < 0.12 and corner_ratio >= 0.5:
                    cands.append(WatermarkCandidate(
                        page_index=pi, kind="image_logo",
                        content=f"重复 Logo (出现{n}页)",
                        bbox=bbox, confidence=0.85,
                        notes=f"在{n}页重复出现的角落/页眉小图，疑似 Logo", xref=xref,
                    ))
                else:
                    cands.append(WatermarkCandidate(
                        page_index=pi, kind="large_image_watermark",
                        content=f"重复图片水印 (出现{n}页, 覆盖约{ratio:.0%})",
                        bbox=bbox, confidence=0.85,
                        notes=f"在{n}页重复出现的图，疑似水印(任何颜色)", xref=xref,
                    ))

        # 去重
        deduped, seen = [], set()
        for c in sorted(cands, key=lambda x: -x.confidence):
            key = (c.page_index, c.kind, round(c.bbox[0] / 10), round(c.bbox[1] / 10), c.content[:30])
            if key not in seen:
                seen.add(key); deduped.append(c)
        high = [c for c in deduped if c.confidence >= 0.65]
        return WatermarkReport(candidates=deduped, high_confidence=high)
    finally:
        doc.close()


# ======================================================================
# 3) 水印清除（图片 Logo + 关键词文字 + 浅灰矢量水印）
# ======================================================================
import re as _re

# 匹配 PDF 内容流里的「填充色」算子（小写 rg / g 为填充，大写 RG / G 为描边，
# 我们只动填充，尽量不碰表格描边线）。
_RG_FILL = _re.compile(rb'(\d?\.\d+) (\d?\.\d+) (\d?\.\d+) rg')
_G_FILL = _re.compile(rb'(\d?\.\d+) g(?=[\s\r\n/\[<(])')


def _whiten_gray_fills(doc, lo: float = 0.55, hi: float = 0.95) -> int:
    """把「近似中性浅灰」的填充色改成白色，让灰色水印在白底上隐形。
    只改浅灰填充，不动黑字、彩色内容、描边线，因此不破坏正文。"""
    def _rg(m):
        try:
            r = float(m.group(1)); g = float(m.group(2)); b = float(m.group(3))
        except Exception:
            return m.group(0)
        if abs(r - g) < 0.06 and abs(g - b) < 0.06 and lo <= (r + g + b) / 3 <= hi:
            return b'1 1 1 rg'
        return m.group(0)

    def _g(m):
        try:
            v = float(m.group(1))
        except Exception:
            return m.group(0)
        return b'1 g' if lo <= v <= hi else m.group(0)

    changed = 0
    for p in doc:
        try:
            xrefs = p.get_contents()
        except Exception:
            continue
        for x in xrefs:
            try:
                raw = doc.xref_stream(x)
            except Exception:
                continue
            new = _RG_FILL.sub(_rg, raw)
            new = _G_FILL.sub(_g, new)
            if new != raw:
                try:
                    doc.update_stream(x, new)
                    changed += 1
                except Exception:
                    pass
    return changed


def create_cleaned_pdf(pdf_path: str, report: WatermarkReport,
                       password: Optional[str] = None,
                       whiten_gray: bool = True) -> str:
    import pymupdf
    high = report.high_confidence or [c for c in report.candidates if c.confidence >= 0.65]
    doc = pymupdf.open(pdf_path)
    try:
        if doc.is_encrypted and password:
            doc.authenticate(password)

        removed_img = 0
        # ① 图片 Logo / 水印（检测阶段已保证只含「多页重复」的图，不会误删正文图）
        xrefs: Dict[int, Set[int]] = {}
        for c in high:
            if c.kind in ("large_image_watermark", "image_logo") and c.xref is not None:
                xrefs.setdefault(c.page_index, set()).add(c.xref)
        for pi, xset in xrefs.items():
            if pi >= len(doc):
                continue
            page = doc[pi]
            for xref in xset:
                try:
                    page.delete_image(xref); removed_img += 1
                except Exception:
                    pass

        # ② 文字水印：只删「关键词类」候选（样本/绝密/内部资料…），
        #    不再盲扫所有浅色大字，避免把表格标题/正文误删。
        removed_txt = 0
        rects: Dict[int, List] = defaultdict(list)
        for c in high:
            if c.kind == "text_watermark":
                rects[c.page_index].append(pymupdf.Rect(c.bbox))
        for pi, rlist in rects.items():
            if pi >= len(doc) or not rlist:
                continue
            page = doc[pi]
            for rr in rlist:
                try:
                    page.add_redact_annot(rr, fill=None); removed_txt += 1
                except Exception:
                    pass
            try:
                page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)
            except TypeError:
                page.apply_redactions()
            except Exception:
                pass

        # ③ 浅灰矢量水印 → 改白隐形（解决「水印难选中」的关键手段）
        removed_vec = _whiten_gray_fills(doc) if whiten_gray else 0

        if removed_img == 0 and removed_txt == 0 and removed_vec == 0:
            return pdf_path
        fd, tmp = tempfile.mkstemp(suffix=".pdf", prefix="pdf2word_clean_")
        os.close(fd)
        doc.save(tmp, garbage=3, deflate=True)
        logger.info("已清除水印 图片=%d 文字=%d 灰色矢量=%d", removed_img, removed_txt, removed_vec)
        return tmp
    finally:
        doc.close()


# ======================================================================
# 3.5) 文字品牌（页眉/页脚重复行）识别与高亮标注（不自动删，交人工）
# ======================================================================
BRANDING_KEYWORDS = [
    "版权所有", "保留所有权利", "官网", "www.", ".com", ".cn", ".net",
    "©", "版权", "客服", "官方", "网校", "教育网", "题库",
]


def detect_text_branding(pdf_path: str, password: Optional[str] = None):
    """找出「每页重复出现、且在页眉/页脚位置 或 含品牌关键词」的文字行。
    返回 [(文字, 出现页数, 位置说明), ...]。只标注、不删除。"""
    import pymupdf
    doc = pymupdf.open(pdf_path)
    try:
        if doc.is_encrypted and password:
            doc.authenticate(password)
        total = max(len(doc), 1)
        thr = max(3, int(total * 0.3))
        line_pages: Dict[str, Set[int]] = defaultdict(set)
        line_zone: Dict[str, str] = {}
        for pi, page in enumerate(doc):
            ph = page.rect.height
            try:
                d = page.get_text("dict")
            except Exception:
                continue
            for b in d.get("blocks", []):
                if b.get("type") != 0:
                    continue
                for l in b.get("lines", []):
                    txt = "".join(s.get("text", "") for s in l.get("spans", [])).strip()
                    if not txt or len(txt) < 4:
                        continue
                    y = l.get("bbox", (0, 0, 0, 0))[1]
                    header = y < ph * 0.12
                    footer = y > ph * 0.88
                    line_pages[txt].add(pi)
                    if header:
                        line_zone[txt] = "页眉"
                    elif footer:
                        line_zone[txt] = "页脚"
        branding = []
        for txt, pages in line_pages.items():
            n = len(pages)
            has_kw = any(k in txt for k in BRANDING_KEYWORDS)
            # 收紧规则：必须「每页重复 + 含品牌关键词(www/.com/版权/官网/网校…)」才算品牌，
            # 避免把「参考答案」「解析」这类正好落在页脚的正文误判为品牌。
            if n >= thr and has_kw and len(txt) < 80:
                branding.append((txt, n, line_zone.get(txt, "正文区")))
        branding.sort(key=lambda x: -x[1])
        return branding
    finally:
        doc.close()


def _highlight_branding(doc, branding_texts) -> int:
    """在 Word 文档对象里，把疑似品牌文字行整段高亮成黄色，方便人工删除。"""
    from docx.enum.text import WD_COLOR_INDEX
    bset = [t for t, _, _ in branding_texts]
    hit = 0

    def proc(p):
        nonlocal hit
        pt = (p.text or "").strip()
        if not pt or len(pt) >= 100:
            return
        for b in bset:
            if b and b in pt:
                for run in p.runs:
                    try:
                        run.font.highlight_color = WD_COLOR_INDEX.YELLOW
                    except Exception:
                        pass
                hit += 1
                return

    for p in doc.paragraphs:
        proc(p)
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                for p in c.paragraphs:
                    proc(p)
    return hit


# ======================================================================
# 3.7) 只去水印、输出干净 PDF（不转 Word）—— 新增功能①
# ======================================================================
@dataclass
class CleanResult:
    success: bool
    output_path: str
    page_count: int
    removed_high: int          # 处理的高置信度水印数
    branding_removed: int      # 涂掉的页眉页脚品牌次数
    messages: List[str]
    error: Optional[str] = None


def _redact_branding_in_pdf(doc, branding) -> int:
    """把「页眉/页脚区」的品牌文字行涂白（只动上/下边缘区域，正文同名文字不碰）。"""
    import pymupdf
    targets = [t for t, _, _ in branding if t]
    count = 0
    for page in doc:
        ph = page.rect.height
        hit_any = False
        for t in targets:
            try:
                rects = page.search_for(t)
            except Exception:
                rects = []
            for r in rects:
                cy = (r.y0 + r.y1) / 2
                if cy < ph * 0.14 or cy > ph * 0.86:  # 仅页眉/页脚区
                    try:
                        page.add_redact_annot(r, fill=(1, 1, 1))
                        count += 1
                        hit_any = True
                    except Exception:
                        pass
        if hit_any:
            try:
                page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)
            except TypeError:
                page.apply_redactions()
            except Exception:
                pass
    return count


def remove_watermarks_to_pdf(pdf_path: str, output_path: str,
                             password: Optional[str] = None,
                             remove_core: bool = True,
                             whiten_gray: bool = True,
                             remove_branding: bool = False) -> CleanResult:
    """只去水印 / Logo，输出干净 PDF（保持 PDF 格式，不转 Word）。
    - remove_core：删「多页重复的图片水印/Logo」+「样本/绝密等关键词文字水印」
    - whiten_gray：把浅灰矢量水印/底纹改白隐形
    - remove_branding：涂掉页眉/页脚重复的品牌文字行
    """
    import pymupdf
    from collections import defaultdict as _dd
    messages: List[str] = []
    try:
        if remove_core:
            report = detect_watermarks(pdf_path, password=password)
            high = report.high_confidence
            messages.append(f"检测到水印候选 {len(report.candidates)} 个（高置信度 {len(high)} 个）")
        else:
            high = []

        branding = []
        if remove_branding:
            try:
                branding = detect_text_branding(pdf_path, password=password)
                if branding:
                    messages.append(f"检测到疑似页眉页脚品牌 {len(branding)} 行，将尝试涂除")
            except Exception:
                branding = []

        doc = pymupdf.open(pdf_path)
        try:
            if doc.is_encrypted and password:
                doc.authenticate(password)
            page_count = len(doc)

            removed_img = 0
            xrefs: Dict[int, Set[int]] = {}
            for c in high:
                if c.kind in ("large_image_watermark", "image_logo") and c.xref is not None:
                    xrefs.setdefault(c.page_index, set()).add(c.xref)
            for pi, xset in xrefs.items():
                if pi >= len(doc):
                    continue
                page = doc[pi]
                for xref in xset:
                    try:
                        page.delete_image(xref); removed_img += 1
                    except Exception:
                        pass

            removed_txt = 0
            rects: Dict[int, List] = _dd(list)
            for c in high:
                if c.kind == "text_watermark":
                    rects[c.page_index].append(pymupdf.Rect(c.bbox))
            for pi, rlist in rects.items():
                if pi >= len(doc) or not rlist:
                    continue
                page = doc[pi]
                for rr in rlist:
                    try:
                        page.add_redact_annot(rr, fill=None); removed_txt += 1
                    except Exception:
                        pass
                try:
                    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)
                except TypeError:
                    page.apply_redactions()
                except Exception:
                    pass

            removed_vec = _whiten_gray_fills(doc) if whiten_gray else 0
            removed_brand = _redact_branding_in_pdf(doc, branding) if branding else 0

            doc.save(output_path, garbage=3, deflate=True)
            total = removed_img + removed_txt + removed_vec + removed_brand
            messages.append(
                f"已清除：图片 {removed_img} / 文字 {removed_txt} / "
                f"灰矢量 {removed_vec} / 品牌 {removed_brand}")
            if total == 0:
                messages.append("未发现可清除的高置信度水印（已原样输出 PDF）")
            return CleanResult(True, output_path, page_count, len(high), removed_brand, messages)
        finally:
            doc.close()
    except Exception as e:
        logger.exception("去水印失败")
        return CleanResult(False, output_path, 0, 0, 0, messages, error=str(e))


# ======================================================================
# 3.6) 去除 pdf2docx 抠出来的"空框图片"（关键词方框等遮挡框）—— 稳妥模式
# ======================================================================
def _remove_empty_boxes(docx_path, mode="safe", min_cy_emu=550000, max_aspect=4.0, max_ink=0.20) -> int:
    """删除"空框图片"。
    - safe(稳妥): 只删「(又矮 或 又宽扁) 且 内容很空」的框；保留流程图等线条大图、密实小图。
    - aggressive(激进): 删掉「所有内容很空的图」(含线条图/流程图)；只保留实心真图片(照片/彩色渲染图)。"""
    try:
        from PIL import Image
        import numpy as np
    except Exception:
        return 0
    import zipfile, io, re as _re2, tempfile
    try:
        zin = zipfile.ZipFile(docx_path)
        xml = zin.read("word/document.xml").decode("utf-8")
        try:
            rels = zin.read("word/_rels/document.xml.rels").decode("utf-8")
        except KeyError:
            rels = ""
    except Exception:
        return 0

    rid2img = {}
    for m in _re2.finditer(r'Id="([^"]+)"[^>]*Target="(?:media/)?([^"]+)"', rels):
        rid2img[m.group(1)] = "word/media/" + m.group(2).split("/")[-1]

    cache = {}
    def ink_ratio(path):
        if path in cache:
            return cache[path]
        try:
            im = Image.open(io.BytesIO(zin.read(path))).convert("RGBA")
            a = np.array(im)
            opaque = a[:, :, 3] > 30
            nonwhite = (a[:, :, 0] < 225) | (a[:, :, 1] < 225) | (a[:, :, 2] < 225)
            r = float((opaque & nonwhite).sum()) / max(a.shape[0] * a.shape[1], 1)
        except Exception:
            r = 1.0  # 读不出就当有内容，保留
        cache[path] = r
        return r

    drawings = _re2.findall(r'<w:drawing>.*?</w:drawing>', xml, _re2.S)
    newxml = xml
    removed = 0
    for d in drawings:
        rid = _re2.search(r'r:embed="([^"]+)"', d)
        if not rid:
            continue
        img = rid2img.get(rid.group(1))
        if not img:
            continue
        m = _re2.search(r'<wp:extent cx="(\d+)" cy="(\d+)"', d)
        if not m:
            continue
        cx, cy = int(m.group(1)), int(m.group(2))
        aspect = cx / cy if cy else 99
        low_ink = ink_ratio(img) < max_ink
        if mode == "aggressive":
            hit = low_ink                       # 任何尺寸的淡图/框都删（含线条图/流程图）
        else:  # safe
            small_or_flat = (cy < min_cy_emu) or (aspect >= max_aspect)
            hit = small_or_flat and low_ink     # 只删又小/又扁 且 空的框
        if hit:
            newxml = newxml.replace(d, "", 1)
            removed += 1
    zin.close()

    if removed == 0:
        return 0
    fd, tmp = tempfile.mkstemp(suffix=".docx")
    os.close(fd)
    with zipfile.ZipFile(docx_path) as z2, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for it in z2.namelist():
            data = newxml.encode("utf-8") if it == "word/document.xml" else z2.read(it)
            zout.writestr(it, data)
    os.replace(tmp, docx_path)
    return removed


# ======================================================================
# 4) 转换引擎
# ======================================================================
@dataclass
class ConversionResult:
    success: bool
    output_path: str
    page_count: int
    messages: List[str]
    error: Optional[str] = None
    manual_notes: List[str] = field(default_factory=list)  # 未自动处理、需人工删除的项


def _render_page(page, dpi: int) -> str:
    import pymupdf
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    fd, p = tempfile.mkstemp(suffix=".png"); os.close(fd)
    pix.save(p)
    return p


def _set_page_size(doc, w_pt, h_pt):
    from docx.shared import Twips
    sec = doc.sections[0]
    sec.page_width = Twips(int(w_pt * 20))
    sec.page_height = Twips(int(h_pt * 20))
    sec.left_margin = sec.right_margin = Twips(36)
    sec.top_margin = sec.bottom_margin = Twips(36)


def _append_summary(doc, report: WatermarkReport, cleaned: bool, branding=None):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    doc.add_page_break()
    t = doc.add_heading("水印 / Logo / 品牌 标注清单", level=1)
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    intro = doc.add_paragraph()
    if cleaned:
        intro.add_run("已自动清除下列高置信度水印（图片 + 灰色矢量水印 + 关键词文字）。"
                      "若仍有个别残留（多为与正文重叠或烧进扫描图的水印），请参照下表人工删除。").italic = True
    else:
        intro.add_run("下列为检测到的水印候选，当前未自动删除（--keep-watermarks）。"
                      "可按位置人工删除。").italic = True

    high = report.high_confidence or [c for c in report.candidates if c.confidence >= 0.65]
    if high:
        doc.add_paragraph(f"已处理的水印/Logo 共 {len(high)} 条：")
        table = doc.add_table(rows=1, cols=5)
        table.style = "Table Grid"
        hdr = table.rows[0].cells
        for i, h in enumerate(["页码", "类型", "内容/描述", "置信度", "备注"]):
            hdr[i].text = h
        kmap = {"text_watermark": "文字水印", "image_logo": "图片 Logo",
                "large_image_watermark": "图片水印"}
        for c in sorted(high, key=lambda c: (c.page_index, c.kind)):
            row = table.add_row().cells
            row[0].text = str(c.page_index + 1)
            row[1].text = kmap.get(c.kind, c.kind)
            row[2].text = c.content[:70]
            row[3].text = f"{c.confidence:.2f}"
            row[4].text = c.notes[:50]
    else:
        doc.add_paragraph("未检测到高置信度水印/Logo。")

    # 文字品牌（页眉页脚）——不自动删，已在正文黄色高亮，此处再列一遍
    if branding:
        doc.add_paragraph()
        p = doc.add_paragraph()
        p.add_run("⚠ 疑似文字品牌 / 页眉页脚（未自动删除）").bold = True
        note = doc.add_paragraph()
        note.add_run("以下文字行疑似为网站/品牌页眉页脚，已在正文中用【黄色高亮】标出，"
                     "请人工确认后手动删除（未自动删，避免误删正文）。").italic = True
        tb = doc.add_table(rows=1, cols=3)
        tb.style = "Table Grid"
        h = tb.rows[0].cells
        for i, x in enumerate(["文字内容", "出现页数", "位置"]):
            h[i].text = x
        for txt, n, zone in branding:
            r = tb.add_row().cells
            r[0].text = txt[:60]
            r[1].text = f"{n} 页"
            r[2].text = zone


def convert(pdf_path: str, output_path: str, password: Optional[str] = None,
            dpi: int = 200, force_image: bool = False,
            clean_watermarks: bool = True, box_mode: str = "safe",
            whiten_gray: bool = True, remove_branding: bool = False) -> ConversionResult:
    """把 PDF 转 Word。去水印能力与「去水印(出PDF)」完全一致，只是最后输出 Word：
    - clean_watermarks：去多页重复图片水印/Logo + 关键词文字水印
    - whiten_gray：去浅灰矢量水印/底纹
    - remove_branding：去页眉/页脚重复品牌文字（勾选=在源头PDF直接涂除，Word里就没有了；
      不勾=保留并在Word正文黄色高亮、并在提示栏列出，供人工删）
    """
    from docx import Document

    messages: List[str] = []
    cleaned_tmp: Optional[str] = None
    try:
        analysis = analyze_document(pdf_path, password=password)
        messages.append(f"文档共 {analysis.page_count} 页")

        # —— 与去水印(出PDF)相同的清洗：先产出一个干净 PDF，再拿去转 Word ——
        actual_pdf = pdf_path
        if clean_watermarks or whiten_gray or remove_branding:
            fd, cleaned_tmp = tempfile.mkstemp(suffix=".pdf", prefix="pdf2word_pre_")
            os.close(fd)
            cr = remove_watermarks_to_pdf(
                pdf_path, cleaned_tmp, password=password,
                remove_core=clean_watermarks, whiten_gray=whiten_gray,
                remove_branding=remove_branding)
            if cr.success:
                actual_pdf = cleaned_tmp
                messages.extend(cr.messages)
            else:
                messages.append("清洗预处理失败，使用原文件继续：" + (cr.error or ""))

        # 未勾「去品牌」时，仍检测品牌用于黄色高亮 + 提示栏列出（供人工删）
        branding = []
        if not remove_branding:
            try:
                branding = detect_text_branding(pdf_path, password=password)
            except Exception:
                branding = []
            if branding:
                messages.append(f"检测到疑似文字品牌 {len(branding)} 行（将黄色高亮，供人工删除）")

        image_pages = [p for p in analysis.pages if p.page_type == PageType.IMAGE]
        ratio = len(image_pages) / max(analysis.page_count, 1)

        Pdf2DocxConverter, p2d_err = _try_import_pdf2docx()

        want_editable = (not force_image) and ratio < 0.7
        if want_editable and Pdf2DocxConverter is None:
            messages.append(
                f"提示：可编辑还原组件 pdf2docx 无法加载，改用整页保图模式。"
                f"（原因：{p2d_err!r}）"
            )
            want_editable = False

        if not want_editable:
            messages.append("采用「整页高清保图」模式")
            result = _convert_images(actual_pdf, output_path, analysis, None,
                                     dpi, password, False, branding)
        else:
            messages.append("采用「高保真可编辑还原」模式")
            try:
                cv = Pdf2DocxConverter(actual_pdf, password=password)
                cv.convert(output_path, start=0, end=None)
                cv.close()
                if box_mode and box_mode != "off":
                    try:
                        nb = _remove_empty_boxes(output_path, mode=box_mode)
                        if nb:
                            _m = "激进" if box_mode == "aggressive" else "稳妥"
                            messages.append(f"已去除 {nb} 个遮挡框（{_m}模式）")
                    except Exception as e:
                        logger.debug("remove_empty_boxes failed: %s", e)
                doc = Document(output_path)
                hl = _highlight_branding(doc, branding) if branding else 0
                if hl:
                    messages.append(f"已在正文黄色高亮 {hl} 处疑似文字品牌（请人工删除）")
                doc.save(output_path)
                messages.append("转换完成")
                result = ConversionResult(True, output_path, analysis.page_count, [])
            except Exception as e:
                messages.append(f"可编辑还原失败，回退保图模式: {e}")
                result = _convert_images(actual_pdf, output_path, analysis, None,
                                         dpi, password, False, branding)

        result.messages = messages + result.messages
        # 只把「未自动处理、需人工删除」的项交给提示栏（页眉页脚品牌文字）
        result.manual_notes = [f"{zone}·{n}页：{txt}" for txt, n, zone in (branding or [])]
        return result
    except Exception as e:
        logger.exception("转换失败")
        return ConversionResult(False, output_path, 0, messages, error=str(e))
    finally:
        if cleaned_tmp and cleaned_tmp != pdf_path and os.path.exists(cleaned_tmp):
            try:
                os.unlink(cleaned_tmp)
            except OSError:
                pass


def _convert_images(pdf_path, output_path, analysis, report, dpi, password, did_clean, branding=None):
    import pymupdf
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches
    doc = Document()
    msgs = []
    pdf = pymupdf.open(pdf_path)
    try:
        if pdf.is_encrypted and password:
            pdf.authenticate(password)
        _set_page_size(doc, analysis.pages[0].width, analysis.pages[0].height)
        temps = []
        for i, page in enumerate(pdf):
            img = _render_page(page, dpi)
            temps.append(img)
            if i > 0:
                doc.add_page_break()
            para = doc.add_paragraph()
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            para.add_run().add_picture(img, width=Inches(page.rect.width / 72.0 - 0.1))
        doc.save(output_path)
        for p in temps:
            try:
                os.unlink(p)
            except OSError:
                pass
        return ConversionResult(True, output_path, len(pdf), msgs)
    finally:
        pdf.close()


# ======================================================================
# 4.5) PDF 拆分 / 合并（新增功能，纯 PyMuPDF，无损、不改动原有逻辑）
# ======================================================================
import fitz as _fitz_sm  # 复用已有 PyMuPDF；命名独立，避免影响上面的代码


@dataclass
class SplitMergeResult:
    """拆分/合并结果。outputs 为生成的文件路径列表。"""
    success: bool
    outputs: List[str] = field(default_factory=list)
    error: str = ""
    messages: List[str] = field(default_factory=list)


def _open_pdf_checked(path: str, password: Optional[str] = None):
    """打开 PDF；若加密则尝试用密码解锁。返回 (doc, err)。"""
    try:
        doc = _fitz_sm.open(path)
    except Exception as e:  # noqa: BLE001
        return None, f"无法打开：{e}"
    if doc.needs_pass:
        if not password:
            doc.close()
            return None, "NEED_PASSWORD"
        if not doc.authenticate(password):
            doc.close()
            return None, "WRONG_PASSWORD"
    return doc, ""


def get_pdf_page_count(path: str, password: Optional[str] = None) -> Tuple[int, str]:
    """返回 (页数, err)。err 为 'NEED_PASSWORD' / 'WRONG_PASSWORD' / 其它错误串。"""
    doc, err = _open_pdf_checked(path, password)
    if err:
        return 0, err
    try:
        return doc.page_count, ""
    finally:
        doc.close()


def parse_ranges(spec: str, page_count: int) -> Tuple[List[Tuple[int, int]], str]:
    """
    解析 "1-5, 6-12, 13-20" 或 "1-5，8，10-12"（中英文逗号都行）。
    返回 (区间列表[(起,止) 1基, 含端点], 错误信息)。校验越界。
    单个数字视为单页区间。
    """
    if not spec or not spec.strip():
        return [], "范围不能为空"
    raw = spec.replace("，", ",").replace("－", "-").replace("~", "-")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return [], "范围不能为空"
    out: List[Tuple[int, int]] = []
    for p in parts:
        if "-" in p:
            a, _, b = p.partition("-")
            a, b = a.strip(), b.strip()
            if not a.isdigit() or not b.isdigit():
                return [], f"无法识别的范围：{p}"
            s, e = int(a), int(b)
        else:
            if not p.isdigit():
                return [], f"无法识别的页码：{p}"
            s = e = int(p)
        if s < 1 or e < 1:
            return [], f"页码要从 1 开始：{p}"
        if s > e:
            return [], f"范围反了（起 > 止）：{p}"
        if e > page_count:
            return [], f"超出总页数（共 {page_count} 页）：{p}"
        out.append((s, e))
    return out, ""


def split_pdf(pdf_path: str, out_dir: str, method: str,
              password: Optional[str] = None,
              per: int = 1, parts: int = 2,
              ranges: Optional[List[Tuple[int, int]]] = None) -> SplitMergeResult:
    """
    拆分 PDF。method:
      'each'   每页一个文件
      'per'    每 per 页一个文件
      'parts'  平均分成 parts 份（尽量均匀）
      'range'  按 ranges（1基, 含端点）逐段导出
    输出文件命名带页码段，绝不覆盖原文件。
    """
    doc, err = _open_pdf_checked(pdf_path, password)
    if err:
        return SplitMergeResult(False, error=err)
    try:
        n = doc.page_count
        stem = Path(pdf_path).stem
        segments: List[Tuple[int, int]] = []  # 0基, 含端点

        if method == "each":
            segments = [(i, i) for i in range(n)]
        elif method == "per":
            step = max(1, int(per))
            for s in range(0, n, step):
                segments.append((s, min(s + step - 1, n - 1)))
        elif method == "parts":
            k = max(1, min(int(parts), n))
            base, extra = divmod(n, k)
            idx = 0
            for j in range(k):
                size = base + (1 if j < extra else 0)
                if size <= 0:
                    continue
                segments.append((idx, idx + size - 1))
                idx += size
        elif method == "range":
            if not ranges:
                return SplitMergeResult(False, error="未提供拆分范围")
            segments = [(a - 1, b - 1) for (a, b) in ranges]
        else:
            return SplitMergeResult(False, error=f"未知拆分方式：{method}")

        os.makedirs(out_dir, exist_ok=True)
        outputs, msgs = [], []
        width = len(str(n))
        for (s, e) in segments:
            new = _fitz_sm.open()
            new.insert_pdf(doc, from_page=s, to_page=e)
            if s == e:
                tag = f"第{s + 1:0{width}d}页"
            else:
                tag = f"第{s + 1:0{width}d}-{e + 1:0{width}d}页"
            outpath = os.path.join(out_dir, f"{stem}_{tag}.pdf")
            outpath = _dedup_path(outpath)
            new.save(outpath)
            new.close()
            outputs.append(outpath)
        msgs.append(f"拆分完成：共 {len(outputs)} 个文件。")
        return SplitMergeResult(True, outputs=outputs, messages=msgs)
    except Exception as e:  # noqa: BLE001
        return SplitMergeResult(False, error=str(e))
    finally:
        doc.close()


def merge_pdfs(items: List[dict], out_path: str) -> SplitMergeResult:
    """
    合并 PDF。items 为有序列表，每项：
      { 'path': str, 'password': Optional[str], 'pages': Optional[List[int]] }
      pages 为 None → 整份；否则为 1基页码列表（逐页挑选，按给定顺序）。
    输出到 out_path（不覆盖，若存在自动改名）。
    """
    if not items:
        return SplitMergeResult(False, error="没有要合并的内容")
    merged = _fitz_sm.open()
    opened = []
    try:
        total_pages = 0
        for it in items:
            doc, err = _open_pdf_checked(it.get("path", ""), it.get("password"))
            if err:
                name = os.path.basename(it.get("path", ""))
                if err == "NEED_PASSWORD":
                    return SplitMergeResult(False, error=f"NEED_PASSWORD::{it.get('path','')}")
                if err == "WRONG_PASSWORD":
                    return SplitMergeResult(False, error=f"WRONG_PASSWORD::{it.get('path','')}")
                return SplitMergeResult(False, error=f"{name}：{err}")
            opened.append(doc)
            pages = it.get("pages")
            if pages is None:
                merged.insert_pdf(doc)
                total_pages += doc.page_count
            else:
                for pg in pages:
                    if pg < 1 or pg > doc.page_count:
                        return SplitMergeResult(
                            False,
                            error=f"{os.path.basename(it.get('path',''))} 第 {pg} 页超出范围")
                    merged.insert_pdf(doc, from_page=pg - 1, to_page=pg - 1)
                    total_pages += 1
        if total_pages == 0:
            return SplitMergeResult(False, error="合并结果为 0 页")
        out_path = _dedup_path(out_path)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        merged.save(out_path)
        return SplitMergeResult(True, outputs=[out_path],
                                messages=[f"合并完成：{total_pages} 页 → {os.path.basename(out_path)}"])
    except Exception as e:  # noqa: BLE001
        return SplitMergeResult(False, error=str(e))
    finally:
        try:
            merged.close()
        except Exception:  # noqa: BLE001
            pass
        for d in opened:
            try:
                d.close()
            except Exception:  # noqa: BLE001
                pass


def _dedup_path(path: str) -> str:
    """若目标文件已存在，自动加 (2)/(3)… 避免覆盖。"""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    i = 2
    while os.path.exists(f"{stem}({i}){ext}"):
        i += 1
    return f"{stem}({i}){ext}"


def list_pdfs_in_folder(folder: str) -> List[str]:
    """列出文件夹内所有 PDF，按文件名自然排序（用于文件夹合并）。"""
    if not os.path.isdir(folder):
        return []
    files = [os.path.join(folder, f) for f in os.listdir(folder)
             if f.lower().endswith(".pdf")]
    files.sort(key=lambda p: os.path.basename(p).lower())
    return files


# ======================================================================
# 5) 命令行入口
# ======================================================================
def main():
    _require_deps()
    parser = argparse.ArgumentParser(
        description="PDF 转 Word 工具（智能分流 + 自动清除水印）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n  python pdf2word.py report.pdf\n"
               "  python pdf2word.py report.pdf -o out.docx\n"
               "  python pdf2word.py report.pdf --keep-watermarks\n"
               "  python pdf2word.py report.pdf --analyze",
    )
    parser.add_argument("pdf", help="输入 PDF 文件")
    parser.add_argument("-o", "--output", help="输出 DOCX 路径（默认与 PDF 同名）")
    parser.add_argument("--password", help="加密 PDF 密码")
    parser.add_argument("--dpi", type=int, default=200, help="保图模式分辨率（默认 200）")
    parser.add_argument("--force-image", action="store_true", help="强制整页保图")
    parser.add_argument("--keep-watermarks", action="store_true",
                        help="只标注、不自动删除水印（默认会自动清除）")
    parser.add_argument("--box-mode", choices=["off", "safe", "aggressive"], default="safe",
                        help="去除关键词空框/遮挡框：off不去 / safe稳妥(默认) / aggressive激进")
    parser.add_argument("--analyze", action="store_true", help="只分析页面/水印，不转换")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
    )

    if not os.path.exists(args.pdf):
        print("找不到文件：", args.pdf)
        sys.exit(1)

    if args.analyze:
        analysis = analyze_document(args.pdf, password=args.password)
        report = detect_watermarks(args.pdf, password=args.password)
        print(f"\n文件: {args.pdf}\n总页数: {analysis.page_count}")
        print("-" * 56)
        for p in analysis.pages:
            print(f"第 {p.page_index+1:>3} 页 | {p.page_type.value:<10} | "
                  f"文字 {p.text_chars:>5} | 图像覆盖 {p.image_cov:.0%}")
        print("-" * 56)
        high = report.high_confidence
        print(f"高置信度水印候选: {len(high)}")
        for c in sorted(high, key=lambda c: c.page_index):
            print(f"  页 {c.page_index+1}: [{c.kind}] {c.content[:40]} (置信度 {c.confidence:.2f})")
        return

    output = args.output or str(Path(args.pdf).with_suffix(".docx"))
    print(f"开始转换: {args.pdf} → {output}")
    result = convert(
        args.pdf, output,
        password=args.password, dpi=args.dpi,
        force_image=args.force_image,
        clean_watermarks=not args.keep_watermarks,
        box_mode=args.box_mode,
    )
    print()
    if result.success:
        print("✅ 转换成功！")
        print("输出文件:", result.output_path)
        print("页数:", result.page_count)
        for m in result.messages:
            print("  ·", m)
    else:
        print("❌ 转换失败:", result.error)
        for m in result.messages:
            print("  ·", m)
        sys.exit(1)


if __name__ == "__main__":
    main()
