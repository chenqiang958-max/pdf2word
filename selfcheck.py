#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
打包环境自检工具
运行后生成 自检报告.txt，把它发给客服即可定位打包失败原因。
"""
import os
import sys
import platform
import shutil
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
LINES = []


def say(s=""):
    print(s)
    LINES.append(str(s))


def check_pkg(mod, pipname=None):
    pipname = pipname or mod
    try:
        m = __import__(mod)
        ver = getattr(m, "__version__", "?")
        say(f"  [OK ] {pipname:16} 版本 {ver}")
        return True
    except Exception as e:
        say(f"  [缺失] {pipname:16} 无法导入：{e!r}")
        return False


def is_valid_ico(path):
    """粗略校验是不是真正的 ICO 文件（不是把 png 改名成 .ico）。"""
    try:
        with open(path, "rb") as f:
            head = f.read(4)
        # ICO 文件头：00 00 01 00
        if head[:4] == b"\x00\x00\x01\x00":
            return True, "标准 ICO"
        if head[:8] == b"\x89PNG"[:4]:
            return False, "其实是 PNG（被改名成 .ico），PyInstaller 不认"
        return False, f"不是标准 ICO（文件头 {head.hex()}）"
    except Exception as e:
        return False, f"读取失败：{e}"


def main():
    say("==================================================")
    say("            打包环境 自检报告")
    say("==================================================")
    say(f"目录：{HERE}")
    say("")

    say("一、Python")
    say(f"  版本：{platform.python_version()}   位数：{struct.calcsize('P')*8} 位")
    say(f"  路径：{sys.executable}")
    if struct.calcsize("P") * 8 != 64:
        say("  [警告] 建议用 64 位 Python 打包。")
    say("")

    say("二、打包依赖组件")
    need = [
        ("PyInstaller", "pyinstaller"),
        ("customtkinter", "customtkinter"),
        ("cryptography", "cryptography"),
        ("pymupdf", "pymupdf"),
        ("docx", "python-docx"),
        ("pdf2docx", "pdf2docx"),
        ("PIL", "pillow"),
    ]
    missing = []
    for mod, pip in need:
        if not check_pkg(mod, pip):
            missing.append(pip)
    say("")

    say("三、源码文件是否齐全")
    for fn in ["pdf2word.py", "pdf2word_gui.py", "license_core.py", "keygen.py"]:
        p = os.path.join(HERE, fn)
        say(f"  {'[OK ]' if os.path.exists(p) else '[缺失]'} {fn}")
    say("")

    say("四、公钥是否已生成")
    lc = os.path.join(HERE, "license_core.py")
    if os.path.exists(lc):
        try:
            txt = open(lc, encoding="utf-8").read()
            if "REPLACE_WITH_PUBLIC_KEY_HEX" in txt:
                say("  [警告] 还没运行 make_keys.py 生成公钥（占位符还在）。")
            else:
                say("  [OK ] 公钥已配置。")
        except Exception as e:
            say(f"  [?] 读取 license_core.py 失败：{e}")
    say("")

    say("五、图标文件 icon_64.ico")
    ico = os.path.join(HERE, "icon_64.ico")
    if not os.path.exists(ico):
        say("  [无] 没找到 icon_64.ico（不影响打包，只是没图标）。")
    else:
        sz = os.path.getsize(ico)
        ok, why = is_valid_ico(ico)
        say(f"  文件大小：{sz} 字节")
        say(f"  {'[OK ]' if ok else '[问题]'} {why}")
        # 用 PIL 进一步验证
        try:
            from PIL import Image
            im = Image.open(ico)
            say(f"  PIL 可读：格式={im.format} 尺寸={im.size} 模式={im.mode}")
        except Exception as e:
            say(f"  [问题] PIL 打不开这个图标：{e}")
            say("         → 图标可能损坏或不是真 ICO，会导致打包失败。")
    say("")

    say("六、磁盘空间")
    try:
        total, used, free = shutil.disk_usage(HERE)
        say(f"  可用空间：{free/1024/1024/1024:.1f} GB")
        if free < 3 * 1024**3:
            say("  [警告] 可用空间不足 3GB，PyInstaller 打包可能失败。")
    except Exception as e:
        say(f"  [?] 读取磁盘空间失败：{e}")
    say("")

    say("七、已生成的 exe（如果有）")
    exe = os.path.join(HERE, "dist", "PDF2Word.exe")
    if os.path.exists(exe):
        sz = os.path.getsize(exe)
        say(f"  dist\\PDF2Word.exe 大小：{sz/1024/1024:.2f} MB")
        if sz < 1024 * 1024:
            say("  [问题] exe 只有几 KB = 打包没成功，或【被杀毒软件删掉了】。")
            say("         最常见原因：Windows安全中心/杀毒把 PyInstaller 的 exe 当病毒隔离。")
            say("         解决：把这个文件夹加入杀毒的“信任/排除”目录，再重新打包。")
    else:
        say("  还没有 dist\\PDF2Word.exe。")
    say("")

    say("==================================================")
    if missing:
        say("结论：缺少组件 -> " + ", ".join(missing))
        say("请先运行：pip install " + " ".join(missing))
    else:
        say("组件齐全。若 exe 仍是几 KB，多半是杀毒软件隔离，请看第七节。")
    say("==================================================")

    out = os.path.join(HERE, "自检报告.txt")
    try:
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(LINES))
        say("")
        say(f"报告已保存到：{out}")
        say("请把 自检报告.txt 发给客服。")
    except Exception as e:
        say(f"保存报告失败：{e}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("自检出错：", e)
    input("\n按回车键关闭...")
