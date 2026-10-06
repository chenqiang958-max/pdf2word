# PDF2Word

PDF 转 Word / PDF 去水印工具，带离线卡密授权。Python + GUI，一键打包成 EXE。

## 功能

- **PDF 转 Word**：把 PDF 文档转换成 Word 文档
- **PDF 去水印**：输出干净的 PDF，不转 Word
- **离线卡密授权**：卖家按时长批量生成激活码（Ed25519 签名），客户粘贴激活即可，无需联网、无需机器码

## 快速开始

前置：Python 3.12（安装时勾选 Add to PATH）

```bash
pip install -r requirements.txt   # cryptography 等依赖
python pdf2word_gui.py            # 启动图形界面
```

或双击 `1_运行软件.bat`。

## 打包成 EXE

```bash
build.bat
```

生成 `dist\PDF2Word.exe`，可直接发给客户。

## 卖家：密钥与发码

> ⚠️ **安全提醒**：本仓库不包含 `private_key.hex`。请先运行 `make_keys.py` 生成你自己的密钥对，**私钥只放自己电脑，绝不公开**。

1. 生成密钥：`python make_keys.py`（自动把公钥写入 `license_core.py`）
2. 重新打包客户端：`build.bat`
3. 发码：`python keygen.py`（图形界面，选时长/数量批量生成）或命令行：

```bash
python keygen.py --days 365 --count 10   # 10 个 365 天的码
python keygen.py --forever --count 5      # 5 个永久码
```

## 文件说明

| 文件 | 说明 |
|---|---|
| `pdf2word_gui.py` | 主程序（GUI，打包入口） |
| `pdf2word.py` | 转换引擎：去水印 / 转 Word |
| `license_core.py` | 授权核心（只含公钥，可随 app 分发） |
| `keygen.py` | 卡密发码工具（卖家专用） |
| `make_keys.py` | 生成密钥对（卖家专用） |
| `使用说明.md` | 详细使用说明 |

## 开源协议

MIT License，详见 [LICENSE](LICENSE)。
