import argparse
import datetime
import os
import re
import zipfile

from aliyundrive_client import download_file_from_aliyundrive, list_backup_files


def load_env(env_path):
    config = {}
    if not os.path.exists(env_path):
        print(f"警告: 配置文件 {env_path} 不存在")
        return config

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip()
    except Exception as e:
        print(f"读取配置文件出错: {e}")

    return config


def list_aliyundrive_backups(config, current_dir):
    try:
        return list_backup_files(config, current_dir=current_dir)
    except Exception as e:
        print(f"获取阿里云盘文件列表失败: {e}")
        return []


def get_backup_name(backup):
    if isinstance(backup, dict):
        return backup.get("name", "")
    return backup


def download_aliyundrive_backup(backup, config, current_dir, local_path):
    name = get_backup_name(backup)
    print(f"正在从阿里云盘下载: {name}...")
    try:
        download_file_from_aliyundrive(backup, local_path, config, current_dir=current_dir)
        print("下载成功")
        return True
    except Exception as e:
        print(f"阿里云盘下载异常: {e}")
        return False


def build_safe_restore_dir(restore_root, timestamp):
    return os.path.join(restore_root, f"VCPToolBox_Restored_{timestamp}")


def ensure_unique_directory(path):
    if not os.path.exists(path):
        return path

    suffix = datetime.datetime.now().strftime("%H%M%S")
    return f"{path}_{suffix}"


def extract_backup_to_directory(zip_path, target_dir):
    os.makedirs(target_dir, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zipf:
        for member in zipf.infolist():
            member_path = os.path.abspath(os.path.join(target_dir, member.filename))
            target_root = os.path.abspath(target_dir)
            if not member_path.startswith(target_root + os.sep) and member_path != target_root:
                raise ValueError(f"压缩包中存在非法路径: {member.filename}")

        zipf.extractall(target_dir)


def extract_timestamp_from_filename(filename):
    match = re.match(r"^VCPToolBox_Backup_(\d{8}_\d{6})\.zip$", filename)
    if match:
        return match.group(1)
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def prompt_backup_choice(files):
    print("可恢复的备份列表:")
    for index, backup in enumerate(files, start=1):
        print(f"  {index}. {get_backup_name(backup)}")

    while True:
        choice = input("请输入要恢复的备份编号: ").strip()
        if not choice.isdigit():
            print("请输入有效数字")
            continue

        index = int(choice)
        if 1 <= index <= len(files):
            return files[index - 1]

        print("编号超出范围，请重新输入")


def prompt_restore_mode():
    print("\n请选择恢复模式:")
    print("  1. 安全解压到独立目录")
    print("  2. 直接覆盖恢复到指定目录")

    while True:
        choice = input("请输入模式编号 [1/2]: ").strip()
        if choice == "1":
            return "safe"
        if choice == "2":
            return "overwrite"
        print("请输入 1 或 2")


def prompt_target_path(default_target):
    while True:
        prompt = "请输入恢复目标目录"
        if default_target:
            prompt += f" (直接回车使用默认值: {default_target})"
        prompt += ": "

        target = input(prompt).strip()
        if target:
            return target
        if default_target:
            return default_target

        print("目标目录不能为空")


def confirm_overwrite(target_dir):
    print("\n警告: 覆盖恢复会覆盖目标目录中的同名文件。")
    print("注意: 该操作不会删除目标目录中额外存在的旧文件。")
    print(f"目标目录: {target_dir}")
    confirm = input('如确认继续，请输入 YES: ').strip()
    return confirm == "YES"


def parse_args():
    parser = argparse.ArgumentParser(description="从阿里云盘 OpenAPI 选择并恢复 VCPToolBox 备份")
    parser.add_argument("--file", help="指定要恢复的远程备份文件名")
    parser.add_argument("--mode", choices=["safe", "overwrite"], help="恢复模式")
    parser.add_argument("--target", help="覆盖恢复时的目标目录")
    parser.add_argument("--yes", action="store_true", help="覆盖恢复时跳过二次确认")
    return parser.parse_args()


def main():
    print("=" * 50)
    print("VCPToolBox 阿里云盘恢复工具")
    print("=" * 50)

    args = parse_args()
    current_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(current_dir, "config.env")
    config = load_env(env_path)

    if config.get("AliyunDriveEnabled", "true").lower() != "true":
        print("错误: 当前脚本仅保留阿里云盘 OpenAPI 恢复，请在 config.env 中设置 AliyunDriveEnabled=true")
        return

    restore_root = config.get("RestoreTempDir", os.path.join(current_dir, "restore"))
    default_target_dir = config.get("VCPToolBoxRestorePath") or config.get("VCPToolBoxPath", "")
    os.makedirs(restore_root, exist_ok=True)

    files = list_aliyundrive_backups(config, current_dir)
    if not files:
        print("未在阿里云盘找到 VCPToolBox 备份文件")
        return

    if args.file:
        selected_backup = next((backup for backup in files if get_backup_name(backup) == args.file), None)
        if not selected_backup:
            print(f"错误: 指定文件不存在于阿里云盘列表中: {args.file}")
            return
    else:
        selected_backup = prompt_backup_choice(files)

    selected_file = get_backup_name(selected_backup)
    mode = args.mode or prompt_restore_mode()
    timestamp = extract_timestamp_from_filename(selected_file)
    local_zip_path = os.path.join(restore_root, selected_file)

    if not download_aliyundrive_backup(selected_backup, config, current_dir, local_zip_path):
        return

    if mode == "safe":
        target_dir = ensure_unique_directory(build_safe_restore_dir(restore_root, timestamp))
        print(f"\n将安全解压到: {target_dir}")
    else:
        target_dir = args.target or prompt_target_path(default_target_dir)
        if not args.yes and not confirm_overwrite(target_dir):
            print("已取消覆盖恢复")
            return

    try:
        extract_backup_to_directory(local_zip_path, target_dir)
    except Exception as e:
        print(f"恢复失败: {e}")
        return

    print("\n" + "=" * 50)
    print("恢复完成")
    print("备份来源: 阿里云盘")
    print(f"备份文件: {selected_file}")
    print(f"恢复目录: {target_dir}")
    print("=" * 50)


if __name__ == "__main__":
    main()
