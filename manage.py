#!/usr/bin/env python
"""Django 项目的命令行入口。"""

import os
import sys


def main():
    # 指定 Django 读取的项目配置模块，后续所有 Django 命令都以此为准。
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        # 从 Django 包中加载命令行工具。
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        # 将底层导入错误转换成开发者能直接处理的提示。
        raise ImportError(
            "无法导入 Django。请先执行：python -m pip install -r requirements.txt"
        ) from exc

    # 把当前命令及其参数交给 Django 命令分发器。
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    # 只有直接运行 manage.py 时才启动命令行流程。
    main()
