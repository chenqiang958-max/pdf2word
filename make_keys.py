#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 Ed25519 密钥对（只需在你自己电脑上运行一次）
================================================
输出：
  1. private_key.hex —— 【私钥】。只放在注册机(keygen)所在文件夹，
     绝对不能随 app 分发给客户！泄露=别人能自己造激活码。
  2. 屏幕打印 + 自动写入 license_core.py 的 PUBLIC_KEY_HEX —— 公钥，
     随 app 分发，泄露无所谓。

用法：
  python make_keys.py            # 生成并自动写入 license_core.py
  python make_keys.py --print    # 只打印，不改文件
"""
import os
import re
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

HERE = os.path.dirname(os.path.abspath(__file__))
PRIV_PATH = os.path.join(HERE, "private_key.hex")
LICENSE_CORE = os.path.join(HERE, "license_core.py")


def main():
    priv = Ed25519PrivateKey.generate()
    priv_raw = priv.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    pub_raw = priv.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    priv_hex = priv_raw.hex()
    pub_hex = pub_raw.hex()

    with open(PRIV_PATH, "w") as f:
        f.write(priv_hex)
    print("私钥已写入：", PRIV_PATH, "  ← 只留注册机，切勿分发！")
    print("公钥(HEX)：", pub_hex)

    if "--print" not in sys.argv and os.path.exists(LICENSE_CORE):
        with open(LICENSE_CORE, "r", encoding="utf-8") as f:
            src = f.read()
        src2 = re.sub(r'PUBLIC_KEY_HEX = "[^"]*"',
                      f'PUBLIC_KEY_HEX = "{pub_hex}"', src, count=1)
        with open(LICENSE_CORE, "w", encoding="utf-8") as f:
            f.write(src2)
        print("已自动写入 license_core.py 的 PUBLIC_KEY_HEX。")
    print("\n完成。请妥善保管 private_key.hex。")


if __name__ == "__main__":
    main()
