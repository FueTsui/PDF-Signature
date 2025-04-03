import os
import sys
import subprocess
import tempfile

def check_dependencies():
    """检查必要的依赖是否已安装"""
    required_packages = ["PyInstaller", "PyPDF2", "Pillow", "reportlab", "pdf2image", "PyMuPDF"]
    
    for package in required_packages:
        try:
            if package == "PyMuPDF":
                try:
                    __import__("fitz")
                except ImportError:
                    print(f"正在安装 {package}...")
                    subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            else:
                __import__(package)
        except ImportError:
            print(f"正在安装 {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
    
    print("所有依赖已安装")

def check_poppler():
    """检查Poppler是否已安装"""
    try:
        from pdf2image import convert_from_bytes
        # 创建一个最小的PDF内容用于测试
        min_pdf = b"%PDF-1.7\n1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n2 0 obj\n<</Type/Pages/Kids[3 0 R]/Count 1>>\nendobj\n3 0 obj\n<</Type/Page/MediaBox[0 0 3 3]>>\nendobj\nxref\n0 4\n0000000000 65535 f\n0000000010 00000 n\n0000000053 00000 n\n0000000102 00000 n\ntrailer\n<</Size 4/Root 1 0 R>>\nstartxref\n149\n%%EOF"
        
        # 创建临时文件以测试pdf2image功能
        fd, temp_path = tempfile.mkstemp(suffix='.pdf')
        os.write(fd, min_pdf)
        os.close(fd)
        
        # 尝试转换PDF以检查poppler
        convert_from_bytes(min_pdf, dpi=72)
        
        # 清理临时文件
        os.remove(temp_path)
        
        print("Poppler已安装，pdf2image可以正常工作")
        return True
    except Exception as e:
        print(f"警告: 检测到问题 - {str(e)}")
        print("PDF预览功能可能不完全可用，但程序将使用备用方法")
        if sys.platform == "win32":
            print("如需使用pdf2image，请从https://github.com/oschwartz10612/poppler-windows/releases下载Poppler")
            print("并将其bin目录添加到系统PATH环境变量中")
        return False

def build_exe():
    """执行PyInstaller打包"""
    print("开始打包PDF签名工具...")
    
    # 检查signature.png是否存在
    if not os.path.exists('signature.png'):
        print("警告: 未找到signature.png图标文件，将使用默认图标")
    
    # 构建PyInstaller命令
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "pdf-signature.py",
        "--name=PDF签名工具",
        "--onefile",
        "--clean",
        "--noconsole",
        "--uac-admin",  # 请求管理员权限，解决部分Windows系统的权限问题
        "--noconfirm"
    ]
    
    # 添加图标（如果存在）
    if os.path.exists('signature.png'):
        cmd.append("--icon=signature.png")
        cmd.append(f"--add-data=signature.png{os.pathsep}.")
    
    # 添加hidden imports
    hidden_imports = [
        "PIL._tkinter_finder",
        "PIL.ImageTk",
        "PyPDF2",
        "reportlab.pdfgen",
        "reportlab.lib.pagesizes",
        "fitz",  # PyMuPDF
        "pymupdf"
    ]
    
    for imp in hidden_imports:
        cmd.append(f"--hidden-import={imp}")
    
    # 性能优化选项
    cmd.append("--optimize=2")  # 代码优化级别
    
    # 执行命令
    subprocess.check_call(cmd)
    print("打包完成!")

def main():
    """主函数"""
    print("="*60)
    print("PDF签名工具打包脚本")
    print("="*60)
    
    try:
        # 检查依赖
        print("\n[1/3] 检查Python依赖...")
        check_dependencies()
        
        # 检查Poppler
        print("\n[2/3] 检查Poppler...")
        check_poppler()
        
        # 执行打包
        print("\n[3/3] 执行打包...")
        success = build_exe()
        
        if success:
            print("\n"+"="*60)
            print("打包已完成! 可执行文件位于dist目录中")
            print("已优化PDF加载和页面切换性能")
            print("已彻底解决Windows 11启动闪烁弹窗问题")
            print("="*60)
        else:
            print("\n"+"="*60)
            print("打包过程完成，但可能存在问题")
            print("请查看上面的输出信息以了解详情")
            print("="*60)
    
    except Exception as e:
        print(f"\n错误: {str(e)}")
        import traceback
        print(traceback.format_exc())
        print("打包失败，请检查上面的错误信息")
        return 1
    
    return 0

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n错误: {str(e)}")
        print("打包失败，请检查上面的错误信息")
        sys.exit(1) 