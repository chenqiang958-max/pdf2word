#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF 转 Word —— 双击入口程序（用于打包成 exe）

行为：双击运行后，自动转换「本程序所在文件夹」里的所有 PDF，
转好的 Word 保存在同一个文件夹，结束弹出完成提示。
客服只需：把本 exe 和 PDF 放同一个文件夹 → 双击 exe。
"""

import os
import sys
import glob


def app_dir() -> str:
    # 打包成 exe 后，用 exe 所在目录；否则用脚本所在目录
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def popup(text: str, title: str = "PDF 转 Word"):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x40)
    except Exception:
        pass


def main():
    import pdf2word as engine

    # 授权校验（未激活则提示并退出）
    try:
        import license_core
        info = license_core.check_status()
        if not info.ok:
            print("软件未激活或授权无效：", info.reason)
            print("请用带界面的 PDF2Word 主程序输入激活码完成激活后再使用。")
            popup("软件未激活。\n请打开 PDF2Word 主程序，输入激活码激活后再使用。")
            input("按回车键关闭...")
            return
    except Exception as e:
        print("授权模块加载失败：", e)
        input("按回车键关闭...")
        return

    folder = app_dir()
    print("=" * 46)
    print("   PDF 转 Word 工具")
    print("=" * 46)
    print("文件夹:", folder)
    print()

    pdfs = sorted(glob.glob(os.path.join(folder, "*.pdf")) +
                  glob.glob(os.path.join(folder, "*.PDF")))
    if not pdfs:
        print("没有找到 PDF 文件。")
        print("请把要转换的 PDF 放到本程序所在的文件夹，然后重新双击运行。")
        popup("没有找到 PDF 文件。\n请把 PDF 放到本程序所在的文件夹，再双击运行。")
        input("按回车键关闭...")
        return

    total = len(pdfs)
    fail = 0
    for i, p in enumerate(pdfs, 1):
        name = os.path.basename(p)
        out = os.path.splitext(p)[0] + ".docx"
        print(f"[{i}/{total}] 正在转换：{name}")
        try:
            r = engine.convert(p, out)
            if r.success:
                print("        完成 ->", os.path.basename(out))
            else:
                print("        失败：", r.error)
                fail += 1
        except Exception as e:
            print("        失败：", e)
            fail += 1

    print("-" * 46)
    print(f"全部结束。共 {total} 个，成功 {total - fail} 个，失败 {fail} 个。")
    print("转好的 Word 就在同一个文件夹里。")
    popup(f"转换完成！\n共 {total} 个，成功 {total - fail} 个，失败 {fail} 个。\n"
          f"Word 文件已保存在同一个文件夹。")
    input("按回车键关闭...")


if __name__ == "__main__":
    main()
