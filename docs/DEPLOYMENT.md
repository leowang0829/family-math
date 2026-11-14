# 部署、更新与备份

一个应用、一个端口和一个私有数据目录。本地 Python 是已验证路径；Dockerfile 使用 Python 3.12、非 root 用户和独立持久化卷。

## 本地启动

运行 `python run.py`，默认地址 `http://127.0.0.1:8921/`，设置页为 `/setup`，数据目录为 `.local/math`。可用 `--data-dir /path/to/private-data` 明确指定数据位置。请勿把含真实学习记录的目录加入 Git。

## Docker

复制 `.env.example` 为 `.env`，填写自己的百炼密钥，再运行 `docker compose up -d --build`。默认仅将端口映射到本机回环地址，数据保存到 `math-data` 命名卷。

## 云端 HTTPS

在后台之前配置 Nginx 或 Caddy，由反向代理提供 HTTPS。按实际部署环境配置域名、证书和网络。在服务启动环境设置：

```text
MATH_BIND=0.0.0.0
MATH_PORT=8921
MATH_DATA_DIR=/data
MATH_PUBLIC_ORIGIN=https://math.example.com
MATH_FAMILY_PASSWORD=由家长自行设置的至少12个字符密码
DASHSCOPE_API_KEY=自己的百炼密钥
```

启动器将家庭密码保存为 PBKDF2-SHA256 校验值。保护环境变量文件；仅为反向代理开放后台端口，覆盖客户端传入的转发头。公网密钥设置入口禁用，维护配置需在后台所在设备上进行。

```caddy
math.example.com {
    reverse_proxy 127.0.0.1:8921
}
```

Compose 用户可在 `.env` 设置 `MATH_PUBLIC_ORIGIN` 和 `MATH_FAMILY_PASSWORD`。服务须通过预期 HTTPS origin 访问，后台直连只用于本机维护。

## 更新与数据保护

更新前备份私有数据。下载或拉取新程序，保持相同数据目录或 Docker 卷，再重启后台。不要把示例内容复制到正在使用的数据目录。

提供 `DASHSCOPE_API_KEY` 环境变量时会更新模型配置；不提供时保留已有配置。家庭密码变量同理。Compose 更新时保持项目名和卷名，`docker compose down -v` 会删除学习数据卷，请勿用于日常更新。

## 备份与恢复

后台提供每日备份及设置页下载。备份包含 SQLite 快照与关联照片，默认排除密钥、密码和会话。完整灾备还应另行妥善保存私有配置。

运行 `python app/restore_backup.py --help` 查看恢复参数。先停止后台，在独立目录演练恢复；恢复工具会保留原始文件，再切换目标数据。统一版的数据格式和目录与旧双版本不同，不应直接覆盖旧服务。

Docker 镜像、实际云网络、证书和实体打印需要在部署环境验证。此公开版本不会自动更新任何既有服务器。
