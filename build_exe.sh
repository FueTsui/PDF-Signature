#!/bin/bash

echo "正在准备打包PDF签名工具..."

# 检查Python是否已安装
if ! command -v python3 &> /dev/null; then
    echo "错误: 未检测到Python，请先安装Python 3"
    exit 1
fi

# 检查是否为管理员权限
if [ "$EUID" -ne 0 ]; then
    echo "提示: 如果安装依赖失败，请尝试使用sudo运行此脚本"
fi

# 检查操作系统类型
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    echo "检测到macOS系统"
    
    # 检查是否安装了poppler
    if ! command -v pdftoppm &> /dev/null; then
        echo "警告: 未检测到poppler，pdf2image需要此依赖"
        echo "建议执行: brew install poppler"
    fi
else
    # Linux
    echo "检测到Linux系统"
    
    # 检查是否安装了poppler-utils
    if ! command -v pdftoppm &> /dev/null; then
        echo "警告: 未检测到poppler-utils，pdf2image需要此依赖"
        echo "建议执行: sudo apt-get install poppler-utils 或相应的包管理命令"
    fi
fi

# 检查是否存在图标文件
if [ ! -f "signature.png" ]; then
    echo "错误: 找不到signature.png图标文件"
    exit 1
fi

# 执行打包脚本
echo "开始打包程序..."
python3 build_exe.py

if [ $? -ne 0 ]; then
    echo "打包过程中出现错误，请检查日志。"
else
    echo "PDF签名工具打包完成!"
    echo "可执行文件位于dist目录中。"
fi

echo
echo "提示：如果运行生成的程序时无法显示PDF预览，请确保安装了poppler:"
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "macOS用户: brew install poppler"
else
    echo "Linux用户: sudo apt-get install poppler-utils (Ubuntu/Debian)"
    echo "或使用您的Linux发行版对应的包管理器命令"
fi 