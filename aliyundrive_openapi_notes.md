# 阿里云盘 OpenAPI 开发资料整理

资料来源：
- https://www.yuque.com/aliyundrive/zpfszx/eam8ls1lmawwwksv
- https://www.yuque.com/aliyundrive/zpfszx/ezlzok
- https://www.yuque.com/aliyundrive/zpfszx/zqkqp6

## 1. Public 公开客户端授权（OAuth 2.0 + PKCE）

适用于没有后端服务安全保存 `client_secret` 的桌面、移动端或纯客户端应用。

关键限制：
- 返回的 `access_token` 默认有效期为 30 天。
- PKCE 公开客户端模式不支持刷新 token，返回数据中 `refresh_token` 不返回。
- 需要在开发者门户把 appId 配置为公开客户端类型。
- 开启公开客户端后存在被冒充客户端的风险，需要自行评估。
- 公开客户端配置与原密钥授权方式不冲突，可同时使用。

### 1.1 发起授权请求

接口：

```http
GET {域名}/oauth/authorize
```

常见域名示例：

```text
https://openapi.alipan.com
```

Query 参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `client_id` | 是 | 创建应用时分配的 appId |
| `redirect_uri` | 是 | 授权后回调 URI，需要 URL encode；云盘会回调 `redirect_uri&code={code}` |
| `scope` | 是 | 授权范围，多个用英文逗号分隔，例如 `user:base,file:all:read,file:all:write` |
| `response_type` | 是 | 仅支持 `code` |
| `state` | 否 | OAuth 推荐参数，用于回调校验、防 CSRF |
| `relogin` | 否 | H5 下 `true` 强制用户登录，默认 `false` |
| `code_challenge` | 否 | 长度 43-128 的随机字符串，PKCE 使用 |
| `code_challenge_method` | 否 | `plain` 或 `S256`；推荐 `S256` |
| `source` | 否 | 默认 `web` |

`code_challenge_method=plain` 时，`code_challenge` 可直接传长度 >= 43 的随机字符串。

`code_challenge_method=S256` 时：

```text
BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
```

授权链接示例：

```text
https://openapi.alipan.com/oauth/authorize?client_id=APP_ID&redirect_uri=oob&scope=user:base,file:all:read,file:all:write&response_type=code&code_challenge=CODE_VERIFIER_OR_CHALLENGE&code_challenge_method=plain
```

### 1.2 用 code 换 AccessToken

接口：

```http
POST {域名}/oauth/access_token
```

说明：
- `code` 10 分钟内有效。
- `code` 只能使用一次。
- PKCE 模式不需要传 `client_secret`。

Body 参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `client_id` | 是 | 应用 appId |
| `client_secret` | 否 | PKCE 模式不传 |
| `grant_type` | 是 | `authorization_code` 或 `refresh_token` |
| `code` | 否 | 授权码，`authorization_code` 模式使用 |
| `refresh_token` | 否 | 刷新 token；PKCE 模式下通常不返回 |
| `code_verifier` | 否 | 拼授权登录链接时生成的原始随机字符串，不是摘要值 |

返回数据：

| 字段 | 说明 |
| --- | --- |
| `token_type` | `Bearer` |
| `access_token` | 后续调用 OpenAPI 的访问凭证 |
| `refresh_token` | PKCE 模式下不返回 |
| `expires_in` | token 有效期，单位秒，默认 30 天 |

后续接口 Header：

```http
Authorization: Bearer {access_token}
```

## 2. 文件上传

### 2.1 创建文件或文件夹

接口：

```http
POST {域名}/adrive/v1.0/openFile/create
```

Header：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `Authorization` | 是 | `Bearer {access_token}` |

Body 参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `drive_id` | 是 | drive id，通过用户空间/drive 信息接口获取 |
| `parent_file_id` | 是 | 父目录 id，上传到根目录填 `root` |
| `name` | 是 | 文件名，UTF-8 最长 1024 字节，不能以 `/` 结尾 |
| `type` | 是 | `file` 或 `folder` |
| `check_name_mode` | 是 | `auto_rename` 自动重命名、`refuse` 同名不创建、`ignore` 同名也创建 |
| `part_info_list` | 否 | 分片列表，最大 10000 个分片 |
| `part_info_list[*].part_number` | 否 | 分片序号，从 1 开始 |
| `pre_hash` | 否 | 文件前 1KB 的 sha1，用于秒传预检测 |
| `size` | 否 | 文件大小，单位 byte；秒传必须。评论区反馈部分上传场景不传可能导致签名错误 |
| `content_hash` | 否 | 文件内容 hash，当前为 sha1；秒传必须 |
| `content_hash_name` | 否 | 默认 `sha1`；秒传必须 |
| `proof_code` | 否 | 秒传必须 |
| `proof_version` | 否 | 固定 `v1` |
| `local_created_at` | 否 | 本地创建时间，格式 `yyyy-MM-dd'T'HH:mm:ss.SSS'Z'` |
| `local_modified_at` | 否 | 本地修改时间，格式 `yyyy-MM-dd'T'HH:mm:ss.SSS'Z'` |
| `streams_info` | 否 | 仅 livp 格式需要，普通场景不需要 |

单个分片限制：
- 最大 5GB。
- 最小 100KB。

返回关键字段：

| 字段 | 说明 |
| --- | --- |
| `drive_id` | drive id |
| `file_id` | 文件 id |
| `status` | 状态 |
| `parent_file_id` | 父目录 id |
| `upload_id` | 上传 id；创建文件夹时为空 |
| `file_name` | 文件名 |
| `available` | 是否可用 |
| `exist` | 是否存在同名文件 |
| `rapid_upload` | 是否秒传成功 |
| `part_info_list[*].part_number` | 分片编号 |
| `part_info_list[*].upload_url` | 该分片上传地址，有效期约 1 小时 |
| `part_info_list[*].part_size` | 分片大小 |

### 2.2 使用 upload_url 上传文件内容

使用 `openFile/create` 返回的 `part_info_list[*].upload_url`，通过 HTTP `PUT` 上传对应文件内容或分片内容。

注意：
- `upload_url` 有效期约 1 小时，过期后需刷新。
- 评论区多次反馈 `403 SignatureDoesNotMatch` 与请求库自动添加 `Content-Type` 有关；上传到 `upload_url` 时建议不要让请求库自动添加不匹配的 `Content-Type`，必要时设为空。
- 评论区反馈 `size` 虽标为选填，但某些场景不传会导致上传签名错误；实现时建议创建文件时传入准确 `size`。

### 2.3 刷新上传地址

接口：

```http
POST {域名}/adrive/v1.0/openFile/getUploadUrl
```

Header：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `Authorization` | 是 | `Bearer {access_token}` |

Body 参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `drive_id` | 是 | drive id |
| `file_id` | 是 | 文件 id |
| `upload_id` | 是 | 创建文件时获取的 upload id |
| `part_info_list` | 是 | 分片信息列表 |
| `part_info_list[*].part_number` | 是 | 分片编号 |

返回包含新的 `part_info_list[*].upload_url`。

### 2.4 列举已上传分片

接口：

```http
POST {域名}/adrive/v1.0/openFile/listUploadedParts
```

Body 参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `drive_id` | 是 | drive id |
| `file_id` | 是 | 文件 id |
| `upload_id` | 是 | 创建文件时获取的 upload id |
| `part_number_marker` | 否 | 分页标记 |

返回关键字段：

| 字段 | 说明 |
| --- | --- |
| `uploaded_parts[*].etag` | 分片 ETag，complete 时可用于校验 |
| `uploaded_parts[*].part_number` | 分片编号 |
| `uploaded_parts[*].part_size` | 分片大小 |
| `next_part_number_marker` | 下一页标记，最后一页为空 |

### 2.5 标记上传完成

接口：

```http
POST {域名}/adrive/v1.0/openFile/complete
```

Body 参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `drive_id` | 是 | drive id |
| `file_id` | 是 | 文件 id |
| `upload_id` | 是 | 创建文件时获取的 upload id |

返回文件信息，包括：`drive_id`、`file_id`、`name`、`size`、`file_extension`、`content_hash`、`category`、`type`、`thumbnail`、`url`、`download_url`、`created_at`、`updated_at`。

### 2.6 推荐上传流程

#### 小文件/单分片上传

1. 获取用户 `drive_id`。
2. 调用 `openFile/create`，传入 `drive_id`、`parent_file_id`、`name`、`type=file`、`check_name_mode`、`size` 和一个 `part_info_list`。
3. 如果返回 `rapid_upload=true`，秒传已完成，可跳过 PUT 和 complete 后续细节。
4. 使用返回的 `upload_url` 执行 HTTP `PUT`。
5. 调用 `openFile/complete` 标记上传完成。

#### 大文件分片上传

1. 本地切分文件。
2. 调用 `openFile/create`，`part_info_list` 中传多个 `part_number`。
3. 分别 PUT 每个分片到对应 `upload_url`。
4. 必要时用 `listUploadedParts` 校验断点续传状态。
5. 调用 `openFile/complete` 合并完成。

#### 秒传逻辑

1. 大文件计算完整 sha1 耗时，可先计算文件前 1KB 的 sha1，放到 `pre_hash`。
2. 如果 `pre_hash` 没有命中，说明无法秒传，可直接普通上传，避免无效完整 sha1 计算。
3. 如果 `pre_hash` 命中，再计算完整 sha1，并传 `content_hash`、`content_hash_name=sha1`、`proof_code`、`proof_version=v1`、`size` 尝试秒传。

## 3. 获取文件列表、搜索、收藏列表

### 3.1 获取文件列表

接口：

```http
POST {域名}/adrive/v1.0/openFile/list
```

说明：获取指定目录下的文件列表。

Body 参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `drive_id` | 是 | drive id |
| `parent_file_id` | 是 | 父目录 id，根目录为 `root` |
| `limit` | 否 | 默认 50，最大 100 |
| `marker` | 否 | 分页标记，使用上一页返回的 `next_marker` |
| `order_by` | 否 | `created_at`、`updated_at`、`name`、`size`、`name_enhanced` |
| `order_direction` | 否 | `DESC` 或 `ASC` |
| `category` | 否 | `video`、`doc`、`audio`、`zip`、`others`、`image`；可逗号组合 |
| `type` | 否 | `all`、`file`、`folder`；默认全部。`type=folder` 时不检查 `category` |
| `video_thumbnail_time` | 否 | 视频缩略图截帧时间，单位 ms，默认 120000 |
| `video_thumbnail_width` | 否 | 视频缩略图宽度，默认 480px |
| `image_thumbnail_width` | 否 | 图片缩略图宽度，默认 480px |
| `fields` | 否 | `*` 返回所有字段，或逗号分隔字段列表 |

`name_enhanced` 适合数字编号排序，例如排序结果是 `1,2,3...99`，而不是 `1,10,11...2`。

返回关键字段：

| 字段 | 说明 |
| --- | --- |
| `items[*].drive_id` | drive id |
| `items[*].file_id` | 文件 id |
| `items[*].parent_file_id` | 父目录 id |
| `items[*].name` | 文件名 |
| `items[*].size` | 文件大小 |
| `items[*].file_extension` | 扩展名 |
| `items[*].content_hash` | 文件 hash |
| `items[*].category` | 分类 |
| `items[*].type` | `file` 或 `folder` |
| `items[*].thumbnail` | 缩略图，评论区说明有效期约 15 分钟 |
| `items[*].url` | 图片预览图地址、小于 5MB 文件下载地址；2024-02-01 起不再返回超过 5MB 文件的 url |
| `items[*].created_at` | 创建时间，格式 `yyyy-MM-dd'T'HH:mm:ss.SSS'Z'` |
| `items[*].updated_at` | 更新时间，格式 `yyyy-MM-dd'T'HH:mm:ss.SSS'Z'` |
| `items[*].play_cursor` | 播放进度 |
| `items[*].video_media_metadata` | 视频信息 |
| `items[*].video_preview_metadata` | 视频预览信息 |
| `next_marker` | 下一页分页标记 |

分页方式：

```text
第一次请求不传 marker。
如果返回 next_marker 非空，下一次请求把 next_marker 作为 marker 传入。
直到 next_marker 为空。
```

### 3.2 文件搜索

接口：

```http
POST {域名}/adrive/v1.0/openFile/search
```

权限：

```text
scope: file:all:read
```

限制：
- `query` 拼接条件不超过 5 个。

Body 参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `drive_id` | 是 | drive id |
| `query` | 是 | 查询语句 |
| `limit` | 否 | 默认 100，最大 100 |
| `marker` | 否 | 分页标记 |
| `order_by` | 否 | `created_at ASC|DESC`、`updated_at ASC|DESC`、`name ASC|DESC`、`size ASC|DESC` |
| `video_thumbnail_time` | 否 | 视频缩略图截帧时间，单位 ms，默认 120000 |
| `video_thumbnail_width` | 否 | 视频缩略图宽度，默认 480px |
| `image_thumbnail_width` | 否 | 图片缩略图宽度，默认 480px |
| `return_total_count` | 否 | 是否返回总数 |

Query 示例：

```text
parent_file_id = '123'
name = '123'
name match "123"
file_extension = 'apk'
created_at < "2019-01-14T00:00:00"
type = 'folder' or name = '123'
parent_file_id = 'root' and name = '123' and category = 'video'
```

返回结构与 list 类似，额外可能返回 `total_count`。

### 3.3 获取收藏文件列表

接口：

```http
POST {域名}/adrive/v1.0/openFile/starredList
```

权限：

```text
scope: file:all:read
```

Body 参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `drive_id` | 是 | drive id |
| `limit` | 否 | 默认 100，最大 100 |
| `marker` | 否 | 分页标记 |
| `order_by` | 否 | `created_at`、`updated_at`、`name`、`size` |
| `order_direction` | 否 | `DESC` 或 `ASC` |
| `type` | 否 | `file` 或 `folder`，默认全部 |
| `video_thumbnail_time` | 否 | 视频缩略图截帧时间，单位 ms，默认 120000 |
| `video_thumbnail_width` | 否 | 视频缩略图宽度，默认 480px |
| `image_thumbnail_width` | 否 | 图片缩略图宽度，默认 480px |

返回结构与 list 类似。

## 4. 备份/恢复功能开发关注点

### 4.1 必需能力

备份到阿里云盘至少需要：

1. PKCE 授权获取 `access_token`。
2. 获取用户 `drive_id`。
3. 查找或创建备份目录。
4. 上传备份文件：小文件单分片，大文件多分片。
5. 上传完成后调用 `complete`。
6. 记录云端 `file_id`、文件名、大小、hash、时间，用于恢复或增量判断。

恢复至少需要：

1. 列出备份目录文件。
2. 根据文件名、时间或 manifest 选择版本。
3. 对超过 5MB 的文件不能依赖 list 返回的 `url`，需要调用下载地址接口 `/adrive/v1.0/openFile/getDownloadUrl`。
4. 下载到本地临时位置并校验。
5. 替换/恢复目标目录。

### 4.2 接口坑点

- `drive_id` 不是路径，需要通过用户 drive/空间信息接口获取。
- `parent_file_id` 也不是路径；根目录为 `root`，子目录必须通过 list/search 找到对应文件夹的 `file_id`。
- `list` 的 `limit` 最大 100，需要循环分页。
- `marker` 是字符串，下一页传上一页返回的 `next_marker`。
- `items[*].url` 对超过 5MB 文件不再返回下载地址，需要使用 `/getDownloadUrl`。
- 缩略图 URL 有效期约 15 分钟，不能长期保存。
- `local_created_at` / `local_modified_at` 在部分列表接口返回中可能为空；若实现同步逻辑，不应只依赖它们。
- 阿里云盘文档中上传 `size` 标为选填，但实际上传实现建议始终传准确大小。
- PUT 到 `upload_url` 时要谨慎处理 `Content-Type`，避免签名不一致。
- 当前文档未体现文件系统变更 watch/增量版本 API，同步功能需要自行基于列表、搜索、manifest 或时间/hash 做扫描。

### 4.3 建议的备份目录结构

```text
/VCPBackups/
  manifest.json
  latest/
    vcptoolbox.zip
    vcpchat.zip
    metadata.json
  snapshots/
    2026-05-13T07-48-00Z/
      vcptoolbox.zip
      vcpchat.zip
      metadata.json
```

`metadata.json` 建议记录：

```json
{
  "created_at": "2026-05-13T07:48:00.000Z",
  "source_machine": "...",
  "files": [
    {
      "name": "vcptoolbox.zip",
      "size": 123456,
      "sha1": "...",
      "drive_id": "...",
      "file_id": "...",
      "parent_file_id": "...",
      "uploaded_at": "..."
    }
  ]
}
```

## 5. 尚需补充的相关接口

当前三篇资料没有展开以下接口，但完成备份/恢复通常还需要继续查：

- 获取用户空间/drive 信息：`/adrive/v1.0/user/getSpaceInfo` 或相关 drive 信息接口。
- 获取文件详情。
- 获取下载地址：`/adrive/v1.0/openFile/getDownloadUrl`。
- 文件更新、移动、复制、删除接口，用于覆盖旧备份或清理历史版本。
