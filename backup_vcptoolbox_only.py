import os
import zipfile
import datetime
import sys

from aliyundrive_client import upload_file_to_aliyundrive


def load_env(env_path):
    config = {}
    if not os.path.exists(env_path):
        print(f"警告: 配置文件 {env_path} 不存在")
        return config

    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    except Exception as e:
        print(f"读取配置文件出错: {e}")

    return config


def backup_vcptoolbox(backup_filename, source_dir='.'):
    """
    仅备份 VCPToolBox 服务端关键文本配置与代码文件。
    沿用原 VCPServerbackup.py 的思路：
    - 只打包关键扩展名
    - 排除大目录与缓存目录
    - 跳过已知大文件/缓存文件
    """
    file_extensions = {
        '.txt', '.md', '.env', '.json', '.js', '.cjs', '.mjs',
        '.py', '.rs', '.toml', '.yml', '.yaml', '.html', '.css', '.vue'
    }
    excluded_dirs = {
        '.git', '__pycache__', 'node_modules', '.venv', 'venv',
        'dist', 'build', 'target', '.next', '.idea', '.vscode'
    }
    excluded_paths = {
        os.path.normpath(os.path.join(source_dir, 'dailynote', 'MusicDiary')),
        os.path.normpath(os.path.join(source_dir, 'image')),
    }
    excluded_files = {
        os.path.normpath(os.path.join(source_dir, r'Plugin\ImageProcessor\multimodal_cache.json')),
        os.path.normpath(os.path.join(source_dir, r'Plugin\TarotDivination\celestial_database.json')),
    }

    print("--- VCPToolBox 后端备份工具 ---")
    print(f"源目录: {source_dir}")

    print("阶段1: 扫描文件...")
    start_time = datetime.datetime.now()
    files_to_backup = []

    for root, dirs, files in os.walk(source_dir):
        root_norm = os.path.normpath(root)
        dirs[:] = [
            d for d in dirs
            if d not in excluded_dirs and os.path.join(root_norm, d) not in excluded_paths
        ]

        for file in files:
            _, ext = os.path.splitext(file)
            if ext in file_extensions:
                file_path = os.path.join(root, file)
                if os.path.normpath(file_path) not in excluded_files:
                    files_to_backup.append(file_path)

    scan_time = (datetime.datetime.now() - start_time).total_seconds()
    print(f"扫描完成: {len(files_to_backup):,} 个文件, 耗时 {scan_time:.2f}s")

    print("阶段2: 压缩文件...")
    compress_start = datetime.datetime.now()
    total = len(files_to_backup)
    update_interval = max(1, total // 20) if total else 1

    with zipfile.ZipFile(backup_filename, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as zipf:
        for i, file_path in enumerate(files_to_backup):
            try:
                zipf.write(file_path, os.path.relpath(file_path, source_dir))
            except (PermissionError, FileNotFoundError):
                pass

            if (i + 1) % update_interval == 0 or (i + 1) == total:
                pct = ((i + 1) / total * 100) if total else 100
                bar_len = 30
                filled = int(bar_len * (i + 1) // total) if total else bar_len
                bar = '█' * filled + '░' * (bar_len - filled)

                elapsed = (datetime.datetime.now() - compress_start).total_seconds()
                speed = (i + 1) / elapsed if elapsed > 0 else 0

                try:
                    sys.stdout.write(f"\r[{bar}] {pct:5.1f}% | {i+1:,}/{total:,} | {speed:.0f} 文件/秒")
                    sys.stdout.flush()
                except UnicodeEncodeError:
                    sys.stdout.write(f"\r> {pct:5.1f}% | {i+1:,}/{total:,} | {speed:.0f} files/s")
                    sys.stdout.flush()

    print()

    total_time = (datetime.datetime.now() - start_time).total_seconds()
    backup_size = os.path.getsize(backup_filename) / (1024 * 1024)

    print('=' * 50)
    try:
        print(f"✅ 备份完成: {backup_filename}")
        print(f"📁 文件数量: {total:,}")
        print(f"📦 大小: {backup_size:.2f} MB")
        print(f"⏱️  总耗时: {total_time:.2f}s")
    except UnicodeEncodeError:
        print(f"DONE: {backup_filename}")
        print(f"Files: {total:,}")
        print(f"Size: {backup_size:.2f} MB")
        print(f"Time: {total_time:.2f}s")


def upload_to_aliyundrive(file_path, config, current_dir):
    print(f"正在上传 {os.path.basename(file_path)} 到阿里云盘...")
    try:
        result = upload_file_to_aliyundrive(file_path, config, current_dir=current_dir)
        name = result.get("name") or result.get("file_name") or os.path.basename(file_path)
        print(f"✅ 阿里云盘上传成功: {name}")
        return True
    except Exception as e:
        print(f"❌ 阿里云盘上传失败: {e}")
        return False


def main():
    print('=' * 50)
    print("VCPToolBox 服务端一键备份")
    print('=' * 50)

    current_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(current_dir, "config.env")
    config = load_env(env_path)

    source_dir = config.get("VCPToolBoxPath", r"D:\VCPHub\VCPToolBox")
    aliyundrive_enabled = config.get("AliyunDriveEnabled", "true").lower() == "true"

    output_dir = os.path.join(current_dir, "backups")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print("配置信息:")
    print(f" - VCPToolBox 路径: {source_dir}")
    print(f" - 阿里云盘上传: {aliyundrive_enabled}")
    print(f" - 本地输出目录: {output_dir}")
    print('-' * 50)

    if not os.path.exists(source_dir):
        print(f"错误: 源目录不存在: {source_dir}")
        return

    if not aliyundrive_enabled:
        print("错误: 当前脚本仅保留阿里云盘 OpenAPI 上传，请在 config.env 中设置 AliyunDriveEnabled=true")
        return

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = os.path.join(output_dir, f"VCPToolBox_Backup_{timestamp}.zip")

    try:
        backup_vcptoolbox(backup_filename, source_dir=source_dir)
    except Exception as e:
        print(f"备份失败: {e}")
        return

    print("\n[2/2] 开始上传到阿里云盘...")
    upload_to_aliyundrive(backup_filename, config, current_dir)

    print("\n" + '=' * 50)
    print("任务处理完毕")
    print('=' * 50)
    if sys.stdin.isatty():
        input("按回车键退出...")


if __name__ == "__main__":
    main()
