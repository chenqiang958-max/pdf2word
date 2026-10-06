#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发码环境自检：把具体失败原因写到 check_keygen_report.txt"""
from __future__ import annotations

import os
import sys
import traceback
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT = os.path.join(HERE, "check_keygen_report.txt")
LINES = []


def say(s=""):
    print(s)
    LINES.append(str(s))


def ok(item, detail=""):
    say("[OK]   {}  {}".format(item, detail).rstrip())


def fail(item, detail=""):
    say("[FAIL] {}  {}".format(item, detail).rstrip())


def warn(item, detail=""):
    say("[WARN] {}  {}".format(item, detail).rstrip())


def main():
    say("=" * 56)
    say("PDF2Word 发码环境自检")
    say("=" * 56)
    say("目录: " + HERE)
    say("解释器: " + sys.executable)
    say("版本:   " + sys.version.replace("\n", " "))
    say("")

    # 1. files
    say("一、必要文件")
    need = ["keygen.py", "license_core.py", "private_key.hex", "make_keys.py"]
    missing = []
    for fn in need:
        p = os.path.join(HERE, fn)
        if os.path.isfile(p):
            ok(fn, "{} 字节".format(os.path.getsize(p)))
        else:
            fail(fn, "当前目录没有这个文件")
            missing.append(fn)
    say("")

    # 2. packages
    say("二、Python 组件")
    pkgs = {
        "cryptography": "发码签名和客户端验签都需要",
        "customtkinter": "发码图形界面需要；没有则会改用系统窗口",
    }
    has_crypto = False
    for mod, why in pkgs.items():
        try:
            m = __import__(mod)
            ver = getattr(m, "__version__", "?")
            ok(mod, "版本 " + str(ver))
            if mod == "cryptography":
                has_crypto = True
        except Exception as e:
            fail(mod, "{} | {}".format(why, e))
            say("       修复: \"{}\" -m pip install {}".format(sys.executable, mod))
    say("")

    # 3. key pair
    say("三、私钥 / 公钥是否配对")
    priv_path = os.path.join(HERE, "private_key.hex")
    core_path = os.path.join(HERE, "license_core.py")
    pub_in_core = None
    if os.path.isfile(core_path):
        txt = open(core_path, encoding="utf-8", errors="replace").read()
        import re
        m = re.search(r'PUBLIC_KEY_HEX\s*=\s*"([0-9a-fA-F]+)"', txt)
        if m:
            pub_in_core = m.group(1).lower()
            ok("license_core 公钥", pub_in_core)
        else:
            fail("license_core 公钥", "未找到 PUBLIC_KEY_HEX")
    if not has_crypto:
        warn("密钥配对", "未安装 cryptography，无法继续验签测试")
    elif os.path.isfile(priv_path):
        raw = open(priv_path, encoding="utf-8", errors="replace").read().strip().replace(" ", "")
        if len(raw) != 64:
            fail("private_key.hex", "应为64位十六进制，实际长度 {}".format(len(raw)))
        else:
            try:
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
                from cryptography.hazmat.primitives import serialization
                priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(raw))
                derived = priv.public_key().public_bytes(
                    serialization.Encoding.Raw, serialization.PublicFormat.Raw
                ).hex()
                ok("私钥可读", os.path.basename(priv_path))
                ok("私钥推导公钥", derived)
                if pub_in_core:
                    if derived == pub_in_core:
                        ok("密钥配对", "私钥与 license_core.py 公钥一致，可以发码")
                    else:
                        fail(
                            "密钥配对",
                            "不一致。用现在的私钥发出的码，旧 exe 会提示激活码无效。"
                            "请运行 make_keys.py 后重新打包客户端。",
                        )
            except Exception as e:
                fail("读取私钥", str(e))
    say("")

    # 4. generate + verify
    say("四、现场试发一枚测试码并验签")
    if has_crypto and os.path.isfile(os.path.join(HERE, "keygen.py")):
        try:
            sys.path.insert(0, HERE)
            import keygen
            import license_core
            code = keygen.make_code(30, "selfcheck")
            ok("生成测试码", code[:24] + "...")
            payload = license_core.parse_and_verify(code)
            ok("客户端验签", "sid={} dur={}".format(payload.get("sid"), payload.get("dur")))
            say("完整测试码（可用来在本机点激活验证）:")
            say(code)
        except Exception as e:
            fail("试发/验签", str(e))
            say(traceback.format_exc())
    else:
        warn("试发/验签", "跳过（缺组件或文件）")
    say("")

    # 5. conclusion
    say("五、结论")
    text = "\n".join(LINES)
    if "[FAIL]" not in text:
        say("自检通过。请运行 2_发码.bat 或: python keygen.py")
    else:
        say("自检未通过。请按上面标了 [FAIL] 的条目处理。")
        if "python.exe not found" in text.lower() or "No python" in text:
            say("优先处理：Python 未进入 PATH。")
        if "cryptography" in text and "[FAIL] cryptography" in text:
            say("优先处理：pip install cryptography")
        if "密钥配对" in text and "[FAIL] 密钥配对" in text:
            say("优先处理：密钥不一致，必须重新打包客户端后再发码。")
    say("=" * 56)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        say("[FAIL] 自检脚本自身异常")
        say(traceback.format_exc())
    try:
        with open(REPORT, "w", encoding="utf-8") as f:
            f.write("\n".join(LINES) + "\n")
        say("")
        say("报告已保存: " + REPORT)
    except Exception as e:
        say("保存报告失败: " + str(e))
    try:
        input("\n按回车关闭...")
    except Exception:
        pass
