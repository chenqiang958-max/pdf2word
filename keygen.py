#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
注册机（卡密发码工具）—— 只给你（卖家）自己用！！
================================================
按“时长”批量生成激活码，不需要客户的机器码。
客户拿到码，在软件里粘贴激活即可，界面显示到期时间。

私钥 private_key.hex 必须和本程序放同一文件夹，且【绝不能】发给客户。

两种用法：
  1) 直接双击 / 无参数运行  → 打开图形界面
  2) 命令行：
       python keygen.py --days 365 --count 10          # 生成10个365天的码
       python keygen.py --forever --count 5            # 生成5个永久码
       python keygen.py --days 30 --count 100 --edition pro
生成的码会同时保存到 codes_日期时间.txt 方便你留档。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import sys
from datetime import date, datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _here() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


HERE = _here()
PRIV_PATH = os.path.join(HERE, "private_key.hex")


def load_private_key() -> Ed25519PrivateKey:
    if not os.path.exists(PRIV_PATH):
        raise FileNotFoundError(
            f"找不到私钥文件：{PRIV_PATH}\n请先运行 make_keys.py 生成密钥对。")
    with open(PRIV_PATH) as f:
        return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(f.read().strip()))


def _new_sid() -> str:
    # 12 位大写十六进制唯一序列号
    return secrets.token_hex(6).upper()


def make_code(dur_days: int = 0, edition: str = "", priv=None) -> str:
    """dur_days=0 表示永久，否则为有效天数（从客户首次激活当天算起）。"""
    if priv is None:
        priv = load_private_key()
    payload = {
        "sid": _new_sid(),
        "dur": int(dur_days) if dur_days else 0,
        "ed": edition or "",
        "is": date.today().isoformat(),
    }
    payload_b = json.dumps(payload, separators=(",", ":"),
                           sort_keys=True, ensure_ascii=False).encode("utf-8")
    sig = priv.sign(payload_b)
    s = base64.b32encode(payload_b + sig).decode().rstrip("=")
    return "-".join(s[i:i + 6] for i in range(0, len(s), 6))


def batch(dur_days: int, count: int, edition: str = "") -> list:
    priv = load_private_key()
    return [make_code(dur_days, edition, priv) for _ in range(max(1, count))]


def save_codes(codes: list, dur_days: int, edition: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(HERE, f"codes_{stamp}.txt")
    dur_txt = "永久" if not dur_days else f"{dur_days}天"
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 生成时间: {datetime.now().isoformat(timespec='seconds')}\n")
        f.write(f"# 时长: {dur_txt}  版本: {edition or '(无)'}  数量: {len(codes)}\n")
        f.write("# 到期时间 = 客户首次激活当天 + 时长\n")
        f.write("#" + "=" * 50 + "\n")
        for i, c in enumerate(codes, 1):
            f.write(f"{i}. {c}\n\n")
    return path


# ----------------------------------------------------------------------
# 图形界面
# ----------------------------------------------------------------------
def run_gui():
    try:
        import customtkinter as ctk
        from tkinter import messagebox
    except Exception:
        print("未安装 customtkinter，无法开图形界面。请用命令行方式。")
        return

    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
    app = ctk.CTk()
    app.title("卡密发码工具 · 卖家专用")
    app.geometry("680x620")

    def font(sz, bold=False):
        return ctk.CTkFont(family="Microsoft YaHei", size=sz, weight="bold" if bold else "normal")

    ctk.CTkLabel(app, text="卡密发码工具", font=font(24, True)).pack(pady=(16, 2))
    ctk.CTkLabel(app, text="⚠ 私钥 private_key.hex 仅本机保存，切勿发给客户",
                 text_color="#c0392b", font=font(12)).pack(pady=(0, 10))

    # 时长
    ctk.CTkLabel(app, text="① 授权时长", anchor="w", font=font(14, True)).pack(fill="x", padx=24)
    dur_mode = ctk.StringVar(value="365天")
    row = ctk.CTkFrame(app, fg_color="transparent"); row.pack(fill="x", padx=24, pady=(4, 4))
    ctk.CTkSegmentedButton(row, values=["永久", "30天", "90天", "365天", "自定义"],
                           variable=dur_mode, font=font(12)).pack(side="left")
    e_custom = ctk.CTkEntry(app, height=36, width=200, font=font(12),
                            placeholder_text="自定义天数，如 180")
    e_custom.pack(fill="x", padx=24, pady=(4, 10))

    # 版本 + 数量
    ctk.CTkLabel(app, text="② 版本（可空）与 数量", anchor="w",
                 font=font(14, True)).pack(fill="x", padx=24)
    row2 = ctk.CTkFrame(app, fg_color="transparent"); row2.pack(fill="x", padx=24, pady=(4, 10))
    e_edition = ctk.CTkEntry(row2, height=38, width=200, font=font(12), placeholder_text="版本，可空")
    e_edition.pack(side="left")
    ctk.CTkLabel(row2, text="  数量：", font=font(13)).pack(side="left")
    e_count = ctk.CTkEntry(row2, height=38, width=100, font=font(12)); e_count.insert(0, "1")
    e_count.pack(side="left")

    out = ctk.CTkTextbox(app, height=230, font=ctk.CTkFont(family="Consolas", size=12))
    out.pack(fill="both", expand=True, padx=24, pady=(6, 6))

    last_codes = {"list": []}   # 保存最近一次生成的激活码，供“复制”按钮使用

    def _dur_days():
        m = dur_mode.get()
        if m == "永久":
            return 0
        if m == "自定义":
            v = e_custom.get().strip()
            if not v.isdigit() or int(v) <= 0:
                raise ValueError("请填写有效的自定义天数")
            return int(v)
        return int(m.replace("天", ""))

    def gen():
        try:
            dur = _dur_days()
            cnt = int(e_count.get().strip() or "1")
            codes = batch(dur, cnt, e_edition.get().strip())
            path = save_codes(codes, dur, e_edition.get().strip())
        except Exception as ex:
            messagebox.showerror("生成失败", str(ex)); return
        dur_txt = "永久" if not dur else f"{dur}天"
        last_codes["list"] = codes
        out.delete("1.0", "end")
        out.insert("end", f"时长：{dur_txt}   数量：{len(codes)}\n"
                          f"（到期 = 客户首次激活当天 + {dur_txt}）\n" + "=" * 40 + "\n")
        for i, c in enumerate(codes, 1):
            out.insert("end", f"{i}. {c}\n\n")
        if len(codes) == 1:
            app.clipboard_clear(); app.clipboard_append(codes[0])
            messagebox.showinfo("完成", f"已生成 1 个激活码并复制到剪贴板。\n已存档：{os.path.basename(path)}")
        else:
            messagebox.showinfo("完成", f"已生成 {len(codes)} 个激活码。\n已存档到：{os.path.basename(path)}")

    def copy_codes():
        codes = last_codes["list"]
        if not codes:
            messagebox.showinfo("提示", "请先点“生成激活码”。")
            return
        app.clipboard_clear()
        app.clipboard_append("\n".join(codes))
        if len(codes) == 1:
            messagebox.showinfo("已复制", "激活码已复制到剪贴板，直接粘贴发给客户即可。")
        else:
            messagebox.showinfo("已复制", f"已复制 {len(codes)} 个激活码到剪贴板（每行一个）。")

    btns = ctk.CTkFrame(app, fg_color="transparent")
    btns.pack(fill="x", padx=24, pady=(0, 16))
    ctk.CTkButton(btns, text="生成激活码（并存档 txt）", height=46, font=font(15, True),
                  command=gen).pack(side="left", fill="x", expand=True)
    ctk.CTkButton(btns, text="复制激活码", height=46, width=140, font=font(15, True),
                  fg_color="#2e7d32", hover_color="#256628",
                  command=copy_codes).pack(side="left", padx=(10, 0))
    app.mainloop()


def main():
    if len(sys.argv) == 1:
        run_gui(); return
    ap = argparse.ArgumentParser(description="卡密发码工具（卖家专用）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--forever", action="store_true", help="永久授权")
    g.add_argument("--days", type=int, help="有效天数（从客户首次激活起算）")
    ap.add_argument("--count", type=int, default=1, help="生成数量")
    ap.add_argument("--edition", default="", help="版本标识，可空")
    args = ap.parse_args()

    dur = 0 if args.forever or not args.days else int(args.days)
    codes = batch(dur, args.count, args.edition)
    path = save_codes(codes, dur, args.edition)
    dur_txt = "永久" if not dur else f"{dur}天"
    print(f"时长：{dur_txt}  数量：{len(codes)}  已存档：{path}\n")
    for i, c in enumerate(codes, 1):
        print(f"{i}. {c}\n")


if __name__ == "__main__":
    main()
