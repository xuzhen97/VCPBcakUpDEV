import datetime
import os
import sys

from VCPServerbackup import backup_user_data_fast
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
    return backup_user_data_fast(backup_filename, source_dir=source_dir)


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
