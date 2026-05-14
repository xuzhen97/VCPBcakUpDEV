# VCPToolBox 阿里云盘备份与恢复

这是一个面向 VCPToolBox 服务端的备份/恢复脚本集合，当前仅保留阿里云盘 OpenAPI 方式。

## 核心功能

- 备份 VCPToolBox 服务端关键文本配置与代码文件
- 使用阿里云盘 OpenAPI Public 客户端 + PKCE 完成授权与上传（默认 `plain`，如确认平台支持可改为 `S256`）
- 从阿里云盘列出备份 zip 并恢复
- 支持安全解压到独立目录或覆盖恢复到目标目录
- 可在 Linux 服务器上运行，首次授权可通过浏览器拿到 `code` 后回填终端

## 文件说明

- `backup_vcptoolbox_only.py`：打包并上传 VCPToolBox 备份到阿里云盘
- `restore_vcptoolbox_from_webdav.py`：从阿里云盘列出并恢复 VCPToolBox 备份
- `aliyundrive_client.py`：阿里云盘 OAuth2 PKCE、目录、上传、列表、下载辅助模块
- `aliyundrive_openapi_notes.md`：整理好的阿里云盘 OpenAPI 开发资料
- `config.env.example`：配置示例

## 配置

复制 `config.env.example` 为 `config.env`，至少填写：

```env
AliyunDriveEnabled=true
AliyunDriveClientId=your_public_app_id
AliyunDriveFolder=VCPToolBox备份
AliyunDriveTokenFile=./aliyundrive_token.json
VCPToolBoxPath=/opt/VCPHub/VCPToolBox
VCPToolBoxRestorePath=/opt/VCPHub/VCPToolBox
RestoreTempDir=/tmp/vcp_restore
```

Windows 环境也可使用：

```env
VCPToolBoxPath=D:\VCPHub\VCPToolBox
VCPToolBoxRestorePath=D:\VCPHub\VCPToolBox
RestoreTempDir=./restore
```

## 备份

```bash
uv run python backup_vcptoolbox_only.py
```

首次授权时：

1. 脚本会打印授权 URL。
2. 在浏览器完成登录授权。
3. 把回调地址中的 `code`，或直接把 `code` 粘贴回终端。

授权成功后，token 会缓存到 `AliyunDriveTokenFile`。

## 恢复

安全恢复到独立目录：

```bash
uv run python restore_vcptoolbox_from_webdav.py --mode safe
```

覆盖恢复到目标目录：

```bash
uv run python restore_vcptoolbox_from_webdav.py --mode overwrite --target /opt/VCPHub/VCPToolBox
```

指定某个备份文件恢复：

```bash
uv run python restore_vcptoolbox_from_webdav.py --file VCPToolBox_Backup_20260513_164051.zip --mode safe
```

## 注意事项

- 当前脚本不再支持 WebDAV/坚果云。
- 阿里云盘 Public 客户端模式没有 `refresh_token`，`access_token` 过期后需要重新授权。
- 当前上传逻辑仍是单文件单分片，单个备份包需要小于 5GB。
- Linux 服务器建议优先使用安全恢复模式验证结果，再做覆盖恢复。
