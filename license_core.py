#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
授权核心模块（纯离线卡密 · 码内含时长）
================================================
本模块随 app 一起分发，只包含【公钥】，无法伪造激活码。

卖法：卖家用注册机(keygen)按“时长”批量生成激活码（不需要客户机器码）。
客户拿到码 → 打开软件 → 粘贴 → 点激活 → 立即可用，界面显示到期时间。

激活码里的载荷 payload（由注册机签发，Ed25519 签名）：
  {
    "sid": "唯一序列号",     # 每个码唯一，用于本机防重置
    "dur": 365,             # 有效天数；0 = 永久
    "ed":  "版本(可空)",
    "is":  "签发日"
  }

到期时间 = 首次激活当天 + dur 天（dur=0 则永久）。

说明（纯离线的固有限制，卖家已知悉）：
  - 同一个码可在多台电脑各自激活（离线无法互相感知）。
  - 首次激活会把授权绑定到本机并记录在注册表，客户在“本机”重装/删档后
    再输同一个码，不会重置时间（用最早那次算起）；但换台电脑不受此限制。
  如需彻底防共享/防重置，需改“联网卡密”，另说。

依赖：cryptography
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

# ----------------------------------------------------------------------
# 【公钥】—— 由 make_keys.py 生成后填入。随 app 分发，泄露也无所谓。
# ----------------------------------------------------------------------
PUBLIC_KEY_HEX = "6033ac3bddb23858591eea0c4bf5ed96bf81bb6abbae06c2519970a6c2769cf9"

# 本地授权文件防篡改用的次级密钥（不是安全边界，只抬高门槛）。可改任意随机串。
_STATE_SECRET = b"pdf2word-state-hmac-key-change-me-2026"

APP_NAME = "PDF2Word"


# ======================================================================
# 机器指纹（这里只用于：把本机授权文件绑定到本机，防止直接拷贝 license.dat 到别的电脑）
# ======================================================================
def _run(cmd) -> str:
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=6)
        return out.decode("utf-8", "ignore")
    except Exception:
        return ""


def _win_board_uuid() -> str:
    s = _run('powershell -NoProfile -Command "(Get-CimInstance Win32_ComputerSystemProduct).UUID"').strip()
    if s and "UUID" not in s.upper():
        return s
    s = _run("wmic csproduct get uuid")
    for line in s.splitlines():
        line = line.strip()
        if line and line.upper() != "UUID":
            return line
    return ""


def _win_disk_serial() -> str:
    s = _run('powershell -NoProfile -Command "(Get-CimInstance Win32_DiskDrive | Select-Object -First 1).SerialNumber"').strip()
    if s:
        return s
    s = _run("wmic diskdrive get serialnumber")
    for line in s.splitlines():
        line = line.strip()
        if line and line.upper() != "SERIALNUMBER":
            return line
    return ""


def _collect_hw() -> str:
    parts = []
    if sys.platform.startswith("win"):
        parts.append(_win_board_uuid())
        parts.append(_win_disk_serial())
    else:
        for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                with open(p) as f:
                    parts.append(f.read().strip()); break
            except Exception:
                pass
        try:
            import uuid as _uuid
            parts.append(format(_uuid.getnode(), "x"))
        except Exception:
            pass
    parts = [p for p in parts if p]
    if not parts:
        parts.append(os.environ.get("COMPUTERNAME", "") or os.environ.get("HOSTNAME", "unknown"))
    return "|".join(parts)


def get_machine_code() -> str:
    raw = _collect_hw()
    h = hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest().upper()
    return "-".join(h[:16][i:i + 4] for i in range(0, 16, 4))


# ======================================================================
# 激活码验签（公钥）
# ======================================================================
def _load_public_key():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    return Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY_HEX))


def _b32d(s: str) -> bytes:
    s = "".join(ch for ch in s if ch not in "-\r\n\t ").upper()
    pad = "=" * (-len(s) % 8)
    return base64.b32decode(s + pad)


def parse_and_verify(activation_code: str) -> dict:
    """解析并验证激活码，返回 payload。验签失败/格式错会抛异常。"""
    from cryptography.exceptions import InvalidSignature
    try:
        blob = _b32d(activation_code)
    except Exception:
        raise ValueError("激活码格式不正确（请检查是否复制完整）")
    if len(blob) <= 64:
        raise ValueError("激活码内容过短")
    payload_b, sig = blob[:-64], blob[-64:]
    pub = _load_public_key()
    try:
        pub.verify(sig, payload_b)
    except InvalidSignature:
        raise ValueError("激活码无效（可能是伪造或输入有误）")
    return json.loads(payload_b.decode("utf-8"))


# ======================================================================
# 本地授权文件 + 注册表标记
# ======================================================================
def _appdata_dir() -> str:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.path.expanduser("~/.config")
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def _license_path() -> str:
    return os.path.join(_appdata_dir(), "license.dat")


def _today() -> date:
    return datetime.now().date()


def _lic_sig(d: dict) -> str:
    msg = "|".join([d.get("code", ""), d.get("sid", ""), d.get("first", ""),
                    d.get("expiry", ""), d.get("machine", ""), d.get("last_run", "")])
    return hmac.new(_STATE_SECRET, msg.encode("utf-8"), hashlib.sha256).hexdigest()


def _read_license() -> Optional[dict]:
    try:
        with open(_license_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_license(d: dict):
    d = dict(d)
    d["sig"] = _lic_sig(d)
    with open(_license_path(), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


# —— 注册表：记录某序列号“本机首次激活日”，用于删档后防重置（仅 Windows，尽力而为）——
def _reg_get_first(sid: str) -> Optional[str]:
    if not sys.platform.startswith("win"):
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\PDF2Word\seen") as k:
            val, _ = winreg.QueryValueEx(k, sid)
            return val
    except Exception:
        return None


def _reg_set_first(sid: str, first: str):
    if not sys.platform.startswith("win"):
        return
    try:
        import winreg
        k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\PDF2Word\seen")
        winreg.SetValueEx(k, sid, 0, winreg.REG_SZ, first)
        winreg.CloseKey(k)
    except Exception:
        pass


# ======================================================================
# 高层接口
# ======================================================================
class LicenseInfo:
    def __init__(self, ok: bool, reason: str = "",
                 expiry: str = "", permanent: bool = False):
        self.ok = ok
        self.reason = reason
        self.expiry = expiry          # "YYYY-MM-DD" 或 ""
        self.permanent = permanent

    def days_left(self) -> Optional[int]:
        if self.permanent or not self.expiry:
            return None
        try:
            exp = datetime.strptime(self.expiry, "%Y-%m-%d").date()
            return (exp - _today()).days
        except Exception:
            return None

    def expiry_text(self) -> str:
        if self.permanent or not self.expiry:
            return "永久"
        dl = self.days_left()
        if dl is None:
            return self.expiry
        return f"{self.expiry}（剩 {dl} 天）" if dl >= 0 else f"{self.expiry}（已过期）"


def _compute_expiry(first: date, dur: int) -> str:
    if not dur or int(dur) <= 0:
        return ""  # 永久
    return (first + timedelta(days=int(dur))).isoformat()


def check_status() -> LicenseInfo:
    """启动时调用：检查本机是否已激活且未过期。"""
    if PUBLIC_KEY_HEX.startswith("REPLACE_"):
        return LicenseInfo(False, "程序未正确配置公钥（开发者请先运行 make_keys.py）")

    d = _read_license()
    if not d or "code" not in d:
        return LicenseInfo(False, "未激活")

    # 授权文件完整性
    if d.get("sig") != _lic_sig(d):
        return LicenseInfo(False, "授权文件损坏或被篡改，请重新激活")
    # 绑定本机（防止直接拷贝 license.dat 到别的电脑）
    if d.get("machine") and d["machine"] != get_machine_code():
        return LicenseInfo(False, "授权与本机不符，请在本机重新激活")

    permanent = not d.get("expiry")
    # 过期检查
    if not permanent:
        try:
            exp = datetime.strptime(d["expiry"], "%Y-%m-%d").date()
        except Exception:
            return LicenseInfo(False, "授权数据异常，请重新激活")
        if _today() > exp:
            return LicenseInfo(False, f"授权已到期（{d['expiry']}），请重新购买激活码")

    # 防改时钟：系统时间早于上次运行 → 判为回拨
    now = datetime.now()
    lr = d.get("last_run", "")
    try:
        if lr and now < datetime.fromisoformat(lr):
            return LicenseInfo(False, "检测到系统时间被回拨，请校正时间后重试")
    except Exception:
        pass
    d["last_run"] = max(now, datetime.fromisoformat(lr)).isoformat(timespec="seconds") \
        if lr else now.isoformat(timespec="seconds")
    _write_license(d)

    return LicenseInfo(True, "", d.get("expiry", ""), permanent)


def activate(activation_code: str) -> LicenseInfo:
    """客户输入激活码后调用。成功则写入本地授权，返回到期信息。"""
    code = (activation_code or "").strip()
    if not code:
        return LicenseInfo(False, "请输入激活码")
    try:
        payload = parse_and_verify(code)
    except Exception as e:
        return LicenseInfo(False, str(e))

    sid = str(payload.get("sid", ""))
    dur = payload.get("dur", 0)

    # 首次激活日：优先取“本机已记录过的最早激活日”（防删档重置），否则今天
    first_str = _reg_get_first(sid)
    existing = _read_license()
    if (not first_str) and existing and existing.get("sid") == sid and existing.get("first"):
        first_str = existing["first"]
    if first_str:
        try:
            first = datetime.strptime(first_str, "%Y-%m-%d").date()
        except Exception:
            first = _today()
    else:
        first = _today()

    expiry = _compute_expiry(first, dur)
    # 若这个码在本机早已过期，别让它重新激活
    if expiry:
        try:
            if _today() > datetime.strptime(expiry, "%Y-%m-%d").date():
                return LicenseInfo(False, f"该激活码在本机已到期（{expiry}）")
        except Exception:
            pass

    d = {
        "code": code,
        "sid": sid,
        "first": first.isoformat(),
        "expiry": expiry,
        "machine": get_machine_code(),
        "last_run": datetime.now().isoformat(timespec="seconds"),
    }
    _write_license(d)
    _reg_set_first(sid, first.isoformat())

    return LicenseInfo(True, "", expiry, not expiry)


# 命令行自检
if __name__ == "__main__":
    info = check_status()
    print("授权状态：", "有效" if info.ok else "无效", "|", info.reason,
          "| 到期:", info.expiry_text() if info.ok else "-")
