#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF 工具 —— 现代化图形界面（婷肥出品）

两大功能，顶部切换：
  ① PDF 去水印（输出干净 PDF，不转 Word）
  ② PDF 转 Word（智能分流 + 去水印 + 附清单）

启动先过【授权】：未激活会弹激活窗，显示本机机器码，输入激活码后方可使用。
"""

import os
import sys
import glob
import threading
import queue

import customtkinter as ctk
from tkinter import filedialog, messagebox

import license_core

BRAND = "婷肥出品"
APP_TITLE = "PDF 工具"

PINK = "#E91E63"
PINK_HOVER = "#C2185B"
PINK_LIGHT = "#ffd6e7"
BLUE = "#2b6cff"
BLUE_HOVER = "#1e51c9"
GREY = "#9aa0a6"
GREY_HOVER = "#7c8288"

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


def _font(size, bold=False):
    return ctk.CTkFont(family="Microsoft YaHei", size=size, weight="bold" if bold else "normal")


def load_engine():
    import pdf2word
    return pdf2word


# ======================================================================
# 激活窗口（未授权时显示）
# ======================================================================
class Activation(ctk.CTk):
    def __init__(self, reason=""):
        super().__init__()
        self.ok = False
        self.title(f"软件激活 · {BRAND}")
        self.geometry("600x440")
        self.minsize(540, 400)
        self.configure(fg_color="#eef1f6")
        self._build(reason)

    def _build(self, reason):
        header = ctk.CTkFrame(self, fg_color=PINK, corner_radius=20)
        header.pack(fill="x", padx=18, pady=(18, 12))
        ctk.CTkLabel(header, text="软件激活", text_color="white",
                     font=_font(26, True)).pack(pady=(16, 0))
        sub = "首次使用需要激活" if reason in ("", "未激活") else f"授权无效：{reason}"
        ctk.CTkLabel(header, text=sub, text_color=PINK_LIGHT,
                     font=_font(13)).pack(pady=(0, 14))

        tip = "请把购买得到的激活码粘贴到下面，点“立即激活”即可使用。"
        ctk.CTkLabel(self, text=tip, anchor="w", justify="left",
                     font=_font(13), text_color="#555").pack(fill="x", padx=24, pady=(4, 8))

        # 激活码
        ctk.CTkLabel(self, text="激活码", anchor="w",
                     font=_font(14, True)).pack(fill="x", padx=24, pady=(4, 2))
        self.t_code = ctk.CTkTextbox(self, height=120, font=ctk.CTkFont(family="Consolas", size=13))
        self.t_code.pack(fill="x", padx=18, pady=(2, 10))

        self.status = ctk.CTkLabel(self, text="", font=_font(12), text_color="#c0392b")
        self.status.pack(fill="x", padx=24)

        ctk.CTkButton(self, text="立 即 激 活", height=50, font=_font(16, True),
                      fg_color=PINK, hover_color=PINK_HOVER,
                      command=self._activate).pack(fill="x", padx=18, pady=(6, 16))

    def _activate(self):
        code = self.t_code.get("1.0", "end").strip()
        if not code:
            self.status.configure(text="请先粘贴激活码。", text_color="#c0392b")
            return
        info = license_core.activate(code)
        if info.ok:
            self.ok = True
            messagebox.showinfo("激活成功",
                                f"激活成功！\n授权到期：{info.expiry_text()}\n\n点击确定进入软件。")
            self.destroy()
        else:
            self.status.configure(text="激活失败：" + info.reason, text_color="#c0392b")


def run_activation(reason="") -> bool:
    win = Activation(reason)
    win.mainloop()
    return win.ok


# ======================================================================
# 主程序
# ======================================================================
class App(ctk.CTk):
    def __init__(self, lic_info=None):
        super().__init__()
        self.lic = lic_info
        exp = self.lic.expiry_text() if self.lic else "永久"
        self.title(f"{APP_TITLE} · {BRAND}　[已授权 · {exp}]")
        self.geometry("900x900")
        self.minsize(820, 820)
        self.configure(fg_color="#eef1f6")

        self.files = []
        self.rows = {}
        self.out_dir = ctk.StringVar(value="")
        self.mode = ctk.StringVar(value="去水印(出PDF)")
        # 去水印选项（两个模式共用，去水印能力一致，只是输出格式不同）
        self.opt_core = ctk.BooleanVar(value=True)      # 去图片水印/Logo + 关键词文字水印
        self.opt_whiten = ctk.BooleanVar(value=True)    # 去浅灰矢量水印/底纹
        self.opt_branding = ctk.BooleanVar(value=True)  # 去页眉/页脚品牌文字
        # 仅转Word用
        self.box_mode = ctk.StringVar(value="稳妥")
        # 【拆分/合并功能】新增状态
        self.split_method = ctk.StringVar(value="每页拆成一个")   # 每页 / 每N页 / 平均份数 / 按范围
        self.split_per = ctk.StringVar(value="10")                # 每N页
        self.split_parts = ctk.StringVar(value="2")               # 平均份数
        self.split_range = ctk.StringVar(value="")                # 按范围，如 1-5, 6-12
        self.merge_mode = ctk.StringVar(value="整份合并")          # 整份合并 / 逐页挑选
        self.pick_pages = {}   # 逐页挑选：path -> 有序页码列表(1基)
        self.q = queue.Queue()

        self._build()
        self._apply_mode()
        self._poll()

    # ---------------- UI ----------------
    def _build(self):
        header = ctk.CTkFrame(self, fg_color=PINK, corner_radius=20)
        header.pack(fill="x", padx=18, pady=(18, 8))
        ctk.CTkLabel(header, text=BRAND, text_color="white",
                     font=_font(26, True)).pack(pady=(14, 0))
        ctk.CTkLabel(header, text=APP_TITLE, text_color=PINK_LIGHT,
                     font=_font(13)).pack(pady=(0, 12))

        # 模式切换
        modebar = ctk.CTkFrame(self, fg_color="transparent")
        modebar.pack(fill="x", padx=18, pady=(2, 6))
        ctk.CTkLabel(modebar, text="功能：", font=_font(14, True)).pack(side="left")
        ctk.CTkSegmentedButton(
            modebar, values=["去水印(出PDF)", "转Word", "拆分", "合并"], variable=self.mode,
            command=lambda _=None: self._apply_mode(),
            selected_color=PINK, selected_hover_color=PINK_HOVER,
            font=_font(14)).pack(side="left", padx=8)

        # ① 文件列表
        ctk.CTkLabel(self, text="①  待处理的 PDF 文件（可添加多个）",
                     font=_font(14, True), anchor="w").pack(fill="x", padx=24, pady=(6, 0))
        self.filelist = ctk.CTkScrollableFrame(self, height=150, corner_radius=16,
                                               fg_color="white")
        self.filelist.pack(fill="x", expand=False, padx=18, pady=(6, 8))

        fb = ctk.CTkFrame(self, fg_color="transparent")
        fb.pack(fill="x", padx=18, pady=(0, 6))
        ctk.CTkButton(fb, text="＋ 添加 PDF 文件", command=self.add_files,
                      corner_radius=14, height=38, font=_font(13),
                      fg_color=BLUE, hover_color=BLUE_HOVER).pack(side="left")
        ctk.CTkButton(fb, text="＋ 添加整个文件夹", command=self.add_folder,
                      corner_radius=14, height=38, font=_font(13),
                      fg_color=BLUE, hover_color=BLUE_HOVER).pack(side="left", padx=8)
        ctk.CTkButton(fb, text="清空列表", command=self.clear,
                      corner_radius=14, height=38, font=_font(13),
                      fg_color=GREY, hover_color=GREY_HOVER).pack(side="left")

        # ② 输出文件夹
        ctk.CTkLabel(self, text="②  输出文件夹",
                     font=_font(14, True), anchor="w").pack(fill="x", padx=24, pady=(8, 0))
        ob = ctk.CTkFrame(self, fg_color="transparent")
        ob.pack(fill="x", padx=18, pady=(6, 6))
        ctk.CTkEntry(ob, textvariable=self.out_dir, corner_radius=14, height=40,
                     font=_font(12)).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(ob, text="选择…", width=88, command=self.choose_out,
                      corner_radius=14, height=40, font=_font(13),
                      fg_color=BLUE, hover_color=BLUE_HOVER).pack(side="left", padx=(8, 0))
        ctk.CTkButton(ob, text="📂 打开", width=96, command=self.open_out,
                      corner_radius=14, height=40, font=_font(13),
                      fg_color="#2e7d32", hover_color="#256628").pack(side="left", padx=(8, 0))

        # ③ 选项区：左边=勾选项，右边=开始按钮+进度（黄框位置）
        self.opt_title = ctk.CTkLabel(self, text="③  选项", font=_font(14, True), anchor="w")
        self.opt_title.pack(fill="x", padx=24, pady=(8, 0))

        opt_row = ctk.CTkFrame(self, fg_color="transparent")
        opt_row.pack(fill="x", padx=18, pady=(4, 4))

        # 左栏：勾选项容器（两个模式在这里切换）
        self.opt_left = ctk.CTkFrame(opt_row, fg_color="transparent")
        self.opt_left.pack(side="left", fill="x", expand=True)

        # 右栏：开始按钮 + 转换进度（就是你圈的黄框位置）
        opt_right = ctk.CTkFrame(opt_row, fg_color="white", corner_radius=16)
        opt_right.pack(side="right", padx=(16, 4), pady=2)
        self.btn = ctk.CTkButton(opt_right, text="开 始 处 理", command=self.start,
                                 fg_color=PINK, hover_color=PINK_HOVER,
                                 corner_radius=16, height=54, width=240,
                                 font=_font(17, True))
        self.btn.pack(padx=18, pady=(16, 10))
        self.prog = ctk.CTkProgressBar(opt_right, corner_radius=10, height=14, width=240,
                                       progress_color=PINK)
        self.prog.set(0)
        self.prog.pack(padx=18, pady=(0, 6))
        self.status_lbl = ctk.CTkLabel(opt_right, text="就绪", font=_font(13, True),
                                       text_color="#666")
        self.status_lbl.pack(padx=18, pady=(0, 16))

        # —— 三个去水印选项（两个模式一致）——
        def _wm_checks(parent):
            ctk.CTkCheckBox(parent, text="去除多页重复的 Logo/图片水印 + 样本/绝密等关键词文字水印",
                            variable=self.opt_core, font=_font(13),
                            fg_color=PINK, hover_color=PINK_HOVER).pack(anchor="w", padx=6, pady=2)
            ctk.CTkCheckBox(parent, text="去除浅灰矢量水印 / 底纹",
                            variable=self.opt_whiten, font=_font(13),
                            fg_color=PINK, hover_color=PINK_HOVER).pack(anchor="w", padx=6, pady=2)
            ctk.CTkCheckBox(parent, text="去除页眉/页脚重复的网址·版权·网校等品牌文字",
                            variable=self.opt_branding, font=_font(13),
                            fg_color=PINK, hover_color=PINK_HOVER).pack(anchor="w", padx=6, pady=2)

        # 去水印(出PDF) 选项面板（放进左栏）
        self.panel_wm = ctk.CTkFrame(self.opt_left, fg_color="transparent")
        _wm_checks(self.panel_wm)
        ctk.CTkLabel(self.panel_wm, text="输出：与原文件同名 + “_已去水印.pdf”，仍是 PDF 格式。",
                     font=_font(11), text_color="#888", anchor="w").pack(fill="x", padx=6, pady=(2, 2))

        # 转Word 选项面板（同样的去水印选项 + 转Word专有的去框）
        self.panel_word = ctk.CTkFrame(self.opt_left, fg_color="transparent")
        _wm_checks(self.panel_word)
        row4 = ctk.CTkFrame(self.panel_word, fg_color="transparent")
        row4.pack(anchor="w", fill="x", padx=6, pady=(2, 4))
        ctk.CTkLabel(row4, text="去除关键词空框 / 遮挡框：", font=_font(13)).pack(side="left")
        ctk.CTkSegmentedButton(row4, values=["不去框", "稳妥", "激进"], variable=self.box_mode,
                               selected_color=PINK, selected_hover_color=PINK_HOVER,
                               font=_font(12)).pack(side="left", padx=8)
        ctk.CTkLabel(self.panel_word, text="输出：与原文件同名的 .docx（可编辑或整页保图）。",
                     font=_font(11), text_color="#888", anchor="w").pack(fill="x", padx=6, pady=(2, 2))

        # ===== 【拆分功能】选项面板 =====
        self.panel_split = ctk.CTkFrame(self.opt_left, fg_color="transparent")
        ctk.CTkLabel(self.panel_split, text="拆分方式（选一种）：",
                     font=_font(13, True), anchor="w").pack(fill="x", padx=6, pady=(2, 2))
        for val, hint in [
            ("每页拆成一个", "一份 PDF → 每一页各存一个文件（最简单，不会出错）"),
            ("每 N 页一个", "比如每 10 页存一个文件"),
            ("平均分成 N 份", "比如 30 页平均分 3 份，自动每份 10 页"),
            ("按范围拆", "比如 1-5, 6-12, 13-20（可自定义每段）"),
        ]:
            rr = ctk.CTkFrame(self.panel_split, fg_color="transparent")
            rr.pack(fill="x", padx=6, pady=1)
            ctk.CTkRadioButton(rr, text=val, variable=self.split_method, value=val,
                               command=self._on_split_method,
                               fg_color=PINK, hover_color=PINK_HOVER,
                               font=_font(13)).pack(side="left")
            ctk.CTkLabel(rr, text="　" + hint, font=_font(11),
                         text_color="#999").pack(side="left")

        # 参数行：每N页 / 份数 / 范围（按方式显隐）
        self.split_param = ctk.CTkFrame(self.panel_split, fg_color="transparent")
        self.split_param.pack(fill="x", padx=6, pady=(4, 2))

        self.row_per = ctk.CTkFrame(self.split_param, fg_color="transparent")
        ctk.CTkLabel(self.row_per, text="每", font=_font(13)).pack(side="left")
        ctk.CTkEntry(self.row_per, textvariable=self.split_per, width=60,
                     font=_font(13)).pack(side="left", padx=4)
        ctk.CTkLabel(self.row_per, text="页存一个文件", font=_font(13)).pack(side="left")

        self.row_parts = ctk.CTkFrame(self.split_param, fg_color="transparent")
        ctk.CTkLabel(self.row_parts, text="平均分成", font=_font(13)).pack(side="left")
        ctk.CTkEntry(self.row_parts, textvariable=self.split_parts, width=60,
                     font=_font(13)).pack(side="left", padx=4)
        ctk.CTkLabel(self.row_parts, text="份", font=_font(13)).pack(side="left")

        self.row_range = ctk.CTkFrame(self.split_param, fg_color="transparent")
        ctk.CTkLabel(self.row_range, text="范围：", font=_font(13)).pack(side="left")
        e_range = ctk.CTkEntry(self.row_range, textvariable=self.split_range, width=260,
                               placeholder_text="例如 1-5, 6-12, 13-20", font=_font(13))
        e_range.pack(side="left", padx=4)
        self.split_range.trace_add("write", lambda *a: self._check_range())
        self.range_hint = ctk.CTkLabel(self.panel_split, text="", font=_font(11),
                                       text_color="#c0392b", anchor="w")
        self.range_hint.pack(fill="x", padx=6, pady=(0, 2))

        ctk.CTkLabel(self.panel_split,
                     text="拆分只针对列表里的【第一个】文件；文件名自动带页码段，不会覆盖原文件。",
                     font=_font(11), text_color="#888", anchor="w").pack(fill="x", padx=6, pady=(2, 2))

        # ===== 【合并功能】选项面板 =====
        self.panel_merge = ctk.CTkFrame(self.opt_left, fg_color="transparent")
        mrow = ctk.CTkFrame(self.panel_merge, fg_color="transparent")
        mrow.pack(fill="x", padx=6, pady=(2, 2))
        ctk.CTkLabel(mrow, text="合并方式：", font=_font(13, True)).pack(side="left")
        ctk.CTkSegmentedButton(mrow, values=["整份合并", "逐页挑选"], variable=self.merge_mode,
                               command=lambda _=None: self._on_merge_mode(),
                               selected_color=PINK, selected_hover_color=PINK_HOVER,
                               font=_font(13)).pack(side="left", padx=8)

        self.merge_hint_full = ctk.CTkLabel(
            self.panel_merge,
            text="把列表里的 PDF 按【从上到下的顺序】整份拼成一个；用右侧 ↑↓ 调整顺序。\n"
                 "「添加整个文件夹」可一次把某文件夹内所有 PDF 按文件名排序加进来。",
            font=_font(11), text_color="#888", anchor="w", justify="left")
        self.merge_hint_full.pack(fill="x", padx=6, pady=(2, 2))

        # 逐页挑选区（高级）
        self.merge_pick_area = ctk.CTkFrame(self.panel_merge, fg_color="transparent")
        ctk.CTkButton(self.merge_pick_area, text="⚙ 打开逐页挑选窗口", command=self._open_pick_window,
                      corner_radius=12, height=34, font=_font(13),
                      fg_color=BLUE, hover_color=BLUE_HOVER).pack(anchor="w", padx=6, pady=(2, 2))
        self.pick_summary = ctk.CTkLabel(self.merge_pick_area, text="尚未挑选任何页面。",
                                         font=_font(11), text_color="#888", anchor="w")
        self.pick_summary.pack(fill="x", padx=6, pady=(0, 2))

        # 处理日志
        ctk.CTkLabel(self, text="处理日志", font=_font(12), anchor="w").pack(
            fill="x", padx=24, pady=(6, 0))
        self.log = ctk.CTkTextbox(self, height=100, corner_radius=14,
                                  fg_color="#1e1e1e", text_color="#e6e6e6",
                                  font=ctk.CTkFont(family="Consolas", size=12))
        self.log.pack(fill="both", expand=True, padx=18, pady=(4, 12))
        self.log.configure(state="disabled")

    def _apply_mode(self):
        # 先全部收起
        for pnl in (self.panel_wm, self.panel_word, self.panel_split, self.panel_merge):
            pnl.pack_forget()
        m = self.mode.get()
        if m.startswith("去水印"):
            self.panel_wm.pack(fill="x", pady=(0, 0))
            self.btn.configure(text="开 始 去 水 印")
        elif m == "转Word":
            self.panel_word.pack(fill="x", pady=(0, 0))
            self.btn.configure(text="开 始 转 Word")
        elif m == "拆分":
            self.panel_split.pack(fill="x", pady=(0, 0))
            self.btn.configure(text="开 始 拆 分")
            self._on_split_method()
        elif m == "合并":
            self.panel_merge.pack(fill="x", pady=(0, 0))
            self.btn.configure(text="开 始 合 并")
            self._on_merge_mode()
        # 合并模式要显示序号与上下移按钮，切换时重刷列表
        self._refresh_filelist()

    # 【拆分功能】根据所选方式，显示对应参数输入行
    def _on_split_method(self):
        for r in (self.row_per, self.row_parts, self.row_range):
            r.pack_forget()
        self.range_hint.configure(text="")
        mth = self.split_method.get()
        if mth == "每 N 页一个":
            self.row_per.pack(fill="x", pady=1)
        elif mth == "平均分成 N 份":
            self.row_parts.pack(fill="x", pady=1)
        elif mth == "按范围拆":
            self.row_range.pack(fill="x", pady=1)
            self._check_range()

    # 【拆分功能】实时校验范围输入，出错标红
    def _check_range(self):
        if self.mode.get() != "拆分" or self.split_method.get() != "按范围拆":
            return
        spec = self.split_range.get().strip()
        if not spec:
            self.range_hint.configure(text="请填写范围，如 1-5, 6-12", text_color="#c0392b")
            return
        if not self.files:
            self.range_hint.configure(text="请先在上方添加要拆分的 PDF。", text_color="#c0392b")
            return
        try:
            engine = load_engine()
            n, err = engine.get_pdf_page_count(self.files[0])
            if err == "NEED_PASSWORD":
                self.range_hint.configure(text="该 PDF 有打开密码，拆分时会要你输入。", text_color="#e67e22")
                return
            if err:
                self.range_hint.configure(text=f"无法读取页数：{err}", text_color="#c0392b")
                return
            ranges, rerr = engine.parse_ranges(spec, n)
            if rerr:
                self.range_hint.configure(text="✗ " + rerr, text_color="#c0392b")
            else:
                seg = "、".join([f"{a}-{b}" if a != b else f"{a}" for a, b in ranges])
                self.range_hint.configure(
                    text=f"✓ 共 {n} 页，将导出 {len(ranges)} 段：{seg}", text_color="#2e7d32")
        except Exception as e:  # noqa: BLE001
            self.range_hint.configure(text=f"校验出错：{e}", text_color="#c0392b")

    # 【合并功能】整份 / 逐页挑选切换
    def _on_merge_mode(self):
        if self.merge_mode.get() == "整份合并":
            self.merge_pick_area.pack_forget()
            self.merge_hint_full.pack(fill="x", padx=6, pady=(2, 2))
        else:
            self.merge_hint_full.pack_forget()
            self.merge_pick_area.pack(fill="x", padx=6, pady=(2, 2))
            self._update_pick_summary()

    # 【合并·逐页挑选】更新已选摘要
    def _update_pick_summary(self):
        total = sum(len(v) for v in self.pick_pages.values() if v)
        picked_files = sum(1 for v in self.pick_pages.values() if v)
        if total == 0:
            self.pick_summary.configure(text="尚未挑选任何页面。")
        else:
            self.pick_summary.configure(
                text=f"已挑选：{picked_files} 个文件、共 {total} 页（将按此顺序合并）。")

    # 【合并·逐页挑选】打开挑选窗口（清单式：文件 → 各页复选框）
    def _open_pick_window(self):
        if not self.files:
            messagebox.showwarning(APP_TITLE, "请先在上方添加要合并的 PDF 文件。")
            return
        try:
            engine = load_engine()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(APP_TITLE, f"引擎加载失败：{e}")
            return

        win = ctk.CTkToplevel(self)
        win.title("逐页挑选要合并的页面")
        win.geometry("560x640")
        win.configure(fg_color="#eef1f6")
        win.transient(self)
        win.after(50, win.grab_set)

        ctk.CTkLabel(win, text="勾选要合并的页面（从上到下、逐个文件按序拼接）",
                     font=_font(14, True)).pack(fill="x", padx=16, pady=(14, 6))

        area = ctk.CTkScrollableFrame(win, fg_color="white", corner_radius=14)
        area.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        # var_map: path -> { page(int) -> BooleanVar }
        var_map = {}
        for p in self.files:
            n, err = engine.get_pdf_page_count(p)
            block = ctk.CTkFrame(area, fg_color="#f7f8fa", corner_radius=12)
            block.pack(fill="x", padx=6, pady=6)
            head = ctk.CTkFrame(block, fg_color="transparent")
            head.pack(fill="x", padx=8, pady=(6, 2))
            ctk.CTkLabel(head, text=os.path.basename(p), font=_font(13, True),
                         anchor="w").pack(side="left", fill="x", expand=True)
            if err:
                ctk.CTkLabel(block, text=f"（无法读取：{err}，如有密码请先在主界面处理）",
                             font=_font(11), text_color="#c0392b").pack(anchor="w", padx=10, pady=(0, 6))
                continue
            var_map[p] = {}
            prev = set(self.pick_pages.get(p, []))

            def _toggle_all(pp=p, total=n):
                allon = all(var_map[pp][k].get() for k in range(1, total + 1))
                for k in range(1, total + 1):
                    var_map[pp][k].set(not allon)
            ctk.CTkButton(head, text="全选/全不选", width=110, height=26, corner_radius=8,
                          command=_toggle_all, fg_color=GREY, hover_color=GREY_HOVER,
                          font=_font(11)).pack(side="right")

            grid = ctk.CTkFrame(block, fg_color="transparent")
            grid.pack(fill="x", padx=10, pady=(2, 8))
            cols = 8
            for pg in range(1, n + 1):
                v = ctk.BooleanVar(value=(pg in prev))
                var_map[p][pg] = v
                cb = ctk.CTkCheckBox(grid, text=str(pg), variable=v, width=44,
                                     font=_font(11), fg_color=PINK, hover_color=PINK_HOVER,
                                     checkbox_width=18, checkbox_height=18)
                r, c = divmod(pg - 1, cols)
                cb.grid(row=r, column=c, padx=3, pady=3, sticky="w")

        def _save():
            new = {}
            for p, pages in var_map.items():
                chosen = [pg for pg in sorted(pages) if pages[pg].get()]
                if chosen:
                    new[p] = chosen
            self.pick_pages = new
            self._update_pick_summary()
            win.destroy()

        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkButton(bar, text="确定", height=40, command=_save,
                      fg_color=PINK, hover_color=PINK_HOVER,
                      font=_font(14, True)).pack(side="right", padx=4)
        ctk.CTkButton(bar, text="取消", height=40, width=90, command=win.destroy,
                      fg_color=GREY, hover_color=GREY_HOVER,
                      font=_font(14)).pack(side="right", padx=4)

    # ---------------- 文件操作 ----------------
    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="选择 PDF 文件", filetypes=[("PDF 文件", "*.pdf"), ("所有文件", "*.*")])
        for p in paths:
            self._add(p)

    def add_folder(self):
        d = filedialog.askdirectory(title="选择包含 PDF 的文件夹")
        if d:
            found = sorted(glob.glob(os.path.join(d, "*.pdf")) +
                           glob.glob(os.path.join(d, "*.PDF")))
            if not found:
                messagebox.showinfo(APP_TITLE, "该文件夹里没有找到 PDF 文件。")
            for p in found:
                self._add(p)

    def _add(self, p):
        if p in self.files:
            return
        self.files.append(p)
        if not self.out_dir.get():
            self.out_dir.set(os.path.dirname(p))
        self._refresh_filelist()

    def _remove(self, p):
        if p in self.files:
            self.files.remove(p)
        self._refresh_filelist()

    # 【拆分/合并功能】上移/下移一行（合并顺序用；其它模式无害）
    def _move(self, p, delta):
        if p not in self.files:
            return
        i = self.files.index(p)
        j = i + delta
        if 0 <= j < len(self.files):
            self.files[i], self.files[j] = self.files[j], self.files[i]
            self._refresh_filelist()

    # 重新渲染文件列表：合并模式显示上下移按钮与序号
    def _refresh_filelist(self):
        for r in list(self.rows.values()):
            try:
                r.destroy()
            except Exception:
                pass
        self.rows = {}
        show_order = self.mode.get() == "合并"
        n = len(self.files)
        for idx, p in enumerate(self.files):
            row = ctk.CTkFrame(self.filelist, fg_color="#f0f2f5", corner_radius=12)
            row.pack(fill="x", pady=3, padx=2)
            if show_order:
                ctk.CTkLabel(row, text=f"{idx + 1}", width=26, anchor="center",
                             font=_font(12, True), text_color=PINK).pack(side="left", padx=(10, 0))
            ctk.CTkLabel(row, text=os.path.basename(p), anchor="w",
                         font=_font(12)).pack(side="left", padx=12, pady=8, fill="x", expand=True)
            ctk.CTkButton(row, text="✕", width=32, height=28, corner_radius=8,
                          command=lambda q=p: self._remove(q),
                          fg_color="#e57373", hover_color="#d9534f",
                          font=_font(12, True)).pack(side="right", padx=8)
            if show_order:
                ctk.CTkButton(row, text="↓", width=30, height=28, corner_radius=8,
                              command=lambda q=p: self._move(q, +1),
                              fg_color=GREY, hover_color=GREY_HOVER,
                              state=("disabled" if idx == n - 1 else "normal"),
                              font=_font(13, True)).pack(side="right", padx=(0, 2))
                ctk.CTkButton(row, text="↑", width=30, height=28, corner_radius=8,
                              command=lambda q=p: self._move(q, -1),
                              fg_color=GREY, hover_color=GREY_HOVER,
                              state=("disabled" if idx == 0 else "normal"),
                              font=_font(13, True)).pack(side="right", padx=(0, 2))
            self.rows[p] = row

    def clear(self):
        for r in self.rows.values():
            r.destroy()
        self.rows = {}
        self.files = []

    def choose_out(self):
        d = filedialog.askdirectory(title="选择输出文件夹")
        if d:
            self.out_dir.set(d)

    def open_out(self):
        d = self.out_dir.get().strip()
        if not d or not os.path.isdir(d):
            messagebox.showinfo(APP_TITLE, "还没有输出文件夹，或该文件夹不存在。\n请先选择输出文件夹或先处理文件。")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(d)
            elif sys.platform == "darwin":
                import subprocess; subprocess.Popen(["open", d])
            else:
                import subprocess; subprocess.Popen(["xdg-open", d])
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"打开文件夹失败：{e}")

    # ---------------- 线程通信 ----------------
    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self.log.configure(state="normal")
                    self.log.insert("end", val + "\n")
                    self.log.see("end")
                    self.log.configure(state="disabled")
                elif kind == "prog":
                    self.prog.set(val)
                elif kind == "status":
                    self.status_lbl.configure(text=val)
                elif kind == "done":
                    self.btn.configure(state="normal")
                    self._apply_mode()
                    self.status_lbl.configure(text="完成")
                    messagebox.showinfo(f"{APP_TITLE} · {BRAND}", val)
        except queue.Empty:
            pass
        self.after(120, self._poll)

    def log_msg(self, s):
        self.q.put(("log", s))

    def start(self):
        if not self.files:
            messagebox.showwarning(APP_TITLE, "请先添加要处理的 PDF 文件。")
            return
        m = self.mode.get()

        # 【拆分/合并】开工前的额外防错
        if m == "拆分":
            if not self._precheck_split():
                return
        elif m == "合并":
            if not self._precheck_merge():
                return

        out = self.out_dir.get().strip() or os.path.dirname(self.files[0])
        if not os.path.isdir(out):
            try:
                os.makedirs(out, exist_ok=True)
            except Exception:
                messagebox.showerror(APP_TITLE, "输出文件夹无效，请重新选择。")
                return
        self.out_dir.set(out)
        self.btn.configure(state="disabled", text="正在处理…")
        self.status_lbl.configure(text="处理中…")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

        core = self.opt_core.get()
        whiten = self.opt_whiten.get()
        branding = self.opt_branding.get()

        if m.startswith("去水印"):
            self.status_lbl.configure(text=f"0 / {len(self.files)}")
            args = (list(self.files), out, core, whiten, branding)
            t = threading.Thread(target=self._worker_wm, args=args, daemon=True)
        elif m == "转Word":
            self.status_lbl.configure(text=f"0 / {len(self.files)}")
            mode_map = {"不去框": "off", "稳妥": "safe", "激进": "aggressive"}
            box_mode = mode_map.get(self.box_mode.get(), "safe")
            args = (list(self.files), out, core, whiten, branding, box_mode)
            t = threading.Thread(target=self._worker_word, args=args, daemon=True)
        elif m == "拆分":
            t = threading.Thread(target=self._worker_split, args=(self.files[0], out),
                                 daemon=True)
        else:  # 合并
            t = threading.Thread(target=self._worker_merge, args=(list(self.files), out),
                                 daemon=True)
        t.start()

    # 【拆分】开工前校验参数
    def _precheck_split(self):
        engine = load_engine()
        p = self.files[0]
        n, err = engine.get_pdf_page_count(p)
        if err == "NEED_PASSWORD":
            pw = self._ask_password(os.path.basename(p))
            if pw is None:
                return False
            self._split_password = pw
            n, err = engine.get_pdf_page_count(p, pw)
            if err:
                messagebox.showerror(APP_TITLE, "密码不正确或文件无法打开。")
                return False
        elif err:
            messagebox.showerror(APP_TITLE, f"无法读取该 PDF：{err}")
            return False
        else:
            self._split_password = None

        mth = self.split_method.get()
        if mth == "每 N 页一个":
            if not self.split_per.get().strip().isdigit() or int(self.split_per.get()) < 1:
                messagebox.showwarning(APP_TITLE, "“每 N 页”请填一个 ≥1 的整数。")
                return False
        elif mth == "平均分成 N 份":
            s = self.split_parts.get().strip()
            if not s.isdigit() or int(s) < 1:
                messagebox.showwarning(APP_TITLE, "“平均分成 N 份”请填一个 ≥1 的整数。")
                return False
            if int(s) > n:
                messagebox.showwarning(APP_TITLE, f"份数不能超过总页数（共 {n} 页）。")
                return False
        elif mth == "按范围拆":
            ranges, rerr = engine.parse_ranges(self.split_range.get(), n)
            if rerr:
                messagebox.showwarning(APP_TITLE, "范围有误：" + rerr)
                return False
        return True

    # 【合并】开工前校验
    def _precheck_merge(self):
        if len(self.files) < 1:
            messagebox.showwarning(APP_TITLE, "请先添加要合并的 PDF。")
            return False
        if self.merge_mode.get() == "整份合并" and len(self.files) < 2:
            if not messagebox.askyesno(APP_TITLE, "只有一个文件，合并结果就是它本身。仍要继续吗？"):
                return False
        if self.merge_mode.get() == "逐页挑选":
            total = sum(len(v) for v in self.pick_pages.values() if v)
            if total == 0:
                messagebox.showwarning(APP_TITLE, "逐页挑选模式下还没有选择任何页面。\n请点“打开逐页挑选窗口”。")
                return False
        return True

    # 弹窗要密码；返回 None 表示取消
    def _ask_password(self, name):
        dlg = ctk.CTkInputDialog(text=f"“{name}”有打开密码，请输入：", title="需要密码")
        val = dlg.get_input()
        if val is None or val == "":
            return None
        return val

    # ---- 去水印(出PDF) worker ----
    def _worker_wm(self, files, out, core, whiten, branding):
        try:
            engine = load_engine()
        except Exception as e:
            self.q.put(("done", f"启动引擎失败：\n{e}"))
            return
        n = len(files); fail = 0
        self.q.put(("prog", 0))
        for i, p in enumerate(files, 1):
            name = os.path.basename(p)
            outpath = os.path.join(out, os.path.splitext(name)[0] + "_已去水印.pdf")
            self.log_msg(f"[{i}/{n}] 去水印：{name}")
            try:
                r = engine.remove_watermarks_to_pdf(
                    p, outpath, remove_core=core, whiten_gray=whiten, remove_branding=branding)
                if getattr(r, "success", False):
                    self.log_msg(f"        ✔ 完成 → {os.path.basename(outpath)}")
                    for m in r.messages:
                        self.log_msg("           · " + m)
                else:
                    self.log_msg(f"        ✗ 失败：{getattr(r, 'error', '未知错误')}")
                    fail += 1
            except Exception as e:
                self.log_msg(f"        ✗ 失败：{e}")
                fail += 1
            self.q.put(("prog", i / n))
            self.q.put(("status", f"{i} / {n}"))
        self.q.put(("done",
                    f"去水印完成！\n共 {n} 个，成功 {n - fail} 个，失败 {fail} 个。\n"
                    f"输出（PDF）在：{out}\n\n—— {BRAND} ——"))

    # ---- 转Word worker ----
    def _worker_word(self, files, out, core, whiten, branding, box_mode):
        try:
            engine = load_engine()
        except Exception as e:
            self.q.put(("done", f"启动转换引擎失败：\n{e}"))
            return
        n = len(files); fail = 0
        manual_total = 0
        self.q.put(("prog", 0))
        for i, p in enumerate(files, 1):
            name = os.path.basename(p)
            outpath = os.path.join(out, os.path.splitext(name)[0] + ".docx")
            self.log_msg(f"[{i}/{n}] 转Word：{name}")
            try:
                r = engine.convert(p, outpath, clean_watermarks=core, box_mode=box_mode,
                                   whiten_gray=whiten, remove_branding=branding)
                if getattr(r, "success", False):
                    self.log_msg(f"        ✔ 完成 → {os.path.basename(outpath)}")
                    notes = getattr(r, "manual_notes", []) or []
                    if notes:
                        manual_total += len(notes)
                        self.log_msg(f"        ⚠ 有 {len(notes)} 处页眉/页脚品牌文字未自动删除（已黄色高亮，需人工删）：")
                        for nt in notes:
                            self.log_msg("            - " + nt)
                else:
                    self.log_msg(f"        ✗ 失败：{getattr(r, 'error', '未知错误')}")
                    fail += 1
            except Exception as e:
                self.log_msg(f"        ✗ 失败：{e}")
                fail += 1
            self.q.put(("prog", i / n))
            self.q.put(("status", f"{i} / {n}"))
        extra = ""
        if manual_total:
            extra = (f"\n\n⚠ 另有 {manual_total} 处页眉/页脚品牌文字需人工删除，\n"
                     f"已在 Word 中【黄色高亮】，详见下方日志。")
        self.q.put(("done",
                    f"转 Word 完成！\n共 {n} 个，成功 {n - fail} 个，失败 {fail} 个。\n"
                    f"输出（Word）在：{out}{extra}\n\n—— {BRAND} ——"))

    # ---- 【拆分】worker ----
    def _worker_split(self, pdf_path, out):
        try:
            engine = load_engine()
        except Exception as e:  # noqa: BLE001
            self.q.put(("done", f"启动引擎失败：\n{e}"))
            return
        pw = getattr(self, "_split_password", None)
        name = os.path.basename(pdf_path)
        self.q.put(("prog", 0))
        self.log_msg(f"拆分：{name}")
        mth = self.split_method.get()
        try:
            if mth == "每页拆成一个":
                r = engine.split_pdf(pdf_path, out, "each", password=pw)
            elif mth == "每 N 页一个":
                r = engine.split_pdf(pdf_path, out, "per", password=pw,
                                     per=int(self.split_per.get()))
            elif mth == "平均分成 N 份":
                r = engine.split_pdf(pdf_path, out, "parts", password=pw,
                                     parts=int(self.split_parts.get()))
            else:
                n, _ = engine.get_pdf_page_count(pdf_path, pw)
                ranges, _ = engine.parse_ranges(self.split_range.get(), n)
                r = engine.split_pdf(pdf_path, out, "range", password=pw, ranges=ranges)
        except Exception as e:  # noqa: BLE001
            self.q.put(("done", f"拆分失败：{e}"))
            return
        self.q.put(("prog", 1))
        if r.success:
            for op in r.outputs:
                self.log_msg("   ✔ " + os.path.basename(op))
            self.q.put(("done",
                        f"拆分完成！\n共生成 {len(r.outputs)} 个文件。\n"
                        f"输出在：{out}\n\n—— {BRAND} ——"))
        else:
            self.log_msg("   ✗ " + r.error)
            self.q.put(("done", f"拆分失败：{r.error}"))

    # ---- 【合并】worker ----
    def _worker_merge(self, files, out):
        try:
            engine = load_engine()
        except Exception as e:  # noqa: BLE001
            self.q.put(("done", f"启动引擎失败：\n{e}"))
            return
        self.q.put(("prog", 0))
        # 组装 items（含密码处理由 merge 里逐个检测；这里先不预填密码，交给下面循环补）
        if self.merge_mode.get() == "整份合并":
            items = [{"path": p} for p in files]
            self.log_msg(f"整份合并：{len(files)} 个文件")
        else:
            items = [{"path": p, "pages": self.pick_pages[p]}
                     for p in files if p in self.pick_pages and self.pick_pages[p]]
            self.log_msg(f"逐页合并：{len(items)} 个文件")

        # 逐个探测是否需要密码，需要就在主线程弹窗
        for it in items:
            n, err = engine.get_pdf_page_count(it["path"])
            if err == "NEED_PASSWORD":
                ev = threading.Event()
                holder = {}

                def _ask(p=it["path"]):
                    holder["pw"] = self._ask_password(os.path.basename(p))
                    ev.set()
                self.after(0, _ask)
                ev.wait()
                pw = holder.get("pw")
                if pw is None:
                    self.q.put(("done", "已取消（有文件需要密码）。"))
                    return
                it["password"] = pw

        out_path = os.path.join(out, "合并结果.pdf")
        try:
            r = engine.merge_pdfs(items, out_path)
        except Exception as e:  # noqa: BLE001
            self.q.put(("done", f"合并失败：{e}"))
            return
        self.q.put(("prog", 1))
        if r.success:
            for m in r.messages:
                self.log_msg("   ✔ " + m)
            self.q.put(("done",
                        f"合并完成！\n{r.messages[0] if r.messages else ''}\n"
                        f"输出在：{out}\n\n—— {BRAND} ——"))
        else:
            self.log_msg("   ✗ " + r.error)
            self.q.put(("done", f"合并失败：{r.error}"))


def main():
    try:
        info = license_core.check_status()
        if not info.ok:
            if not run_activation(info.reason):
                return  # 用户未激活直接关闭
            info = license_core.check_status()
            if not info.ok:
                messagebox.showerror("无法启动", "授权仍无效：" + info.reason)
                return
        app = App(info)
        app.mainloop()
    except Exception as e:
        try:
            messagebox.showerror("启动失败", str(e))
        except Exception:
            print("启动失败:", e)


if __name__ == "__main__":
    main()
