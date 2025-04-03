import os
import tkinter as tk
from tkinter import filedialog, messagebox, Scale, ttk, simpledialog
import PyPDF2
from PIL import Image, ImageTk
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PyPDF2 import PdfReader, PdfWriter
import io
import sys
import json
import tempfile
import subprocess
import hashlib
import base64
import uuid
import datetime
import re
import platform
import socket
import threading
import ctypes

# ========== 打包说明 ==========
# Windows 11上打包命令 (确保无闪烁弹窗):
# pyinstaller --noconsole --windowed --onefile --icon=signature.png --name="PDF签名工具" pdf-signature.py
# 
# 确保以下选项:
# --noconsole: 不显示控制台窗口
# --windowed: 创建Windows应用程序而非控制台应用程序
# --onefile: 打包为单个可执行文件
# 
# 如果仍有闪烁问题，可尝试添加以下选项:
# --add-binary "path\to\required_dll.dll;." : 如果有特定DLL需要包含
# --clean: 在构建前清除PyInstaller缓存
# =============================

# Windows系统控制台隐藏处理
if platform.system() == 'Windows':
    # 检查是否是打包后的exe运行
    if getattr(sys, 'frozen', False):
        # 尝试多种方法彻底隐藏控制台窗口
        try:
            # 重定向标准输出和标准错误到null设备
            sys.stdout = open(os.devnull, 'w')
            sys.stderr = open(os.devnull, 'w')
            
            # 使用kernel32和user32 API彻底隐藏控制台
            kernel32 = ctypes.WinDLL('kernel32')
            user32 = ctypes.WinDLL('user32')
            
            # 尝试多种方式隐藏控制台窗口
            kernel32.FreeConsole()
            
            # 获取并隐藏控制台窗口句柄
            hwnd = kernel32.GetConsoleWindow()
            if hwnd:
                user32.ShowWindow(hwnd, 0)  # SW_HIDE = 0
            
            # 禁用Python的垃圾回收器，防止其在启动阶段引起的停顿
            import gc
            gc.disable()
            
            # 稍后重新启用垃圾回收
            def enable_gc_later():
                gc.enable()
            
            # 使用线程延迟启用垃圾回收
            threading.Timer(2.0, enable_gc_later).start()
        except Exception as e:
            # 即使出错也不输出，保持静默
            pass

class PDFSignatureTool:
    def __init__(self, root):
        # 设置窗口的初始不透明度为0，以避免闪烁
        root.attributes('-alpha', 0.0)
        
        self.root = root
        self.root.title("PDF签名工具")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # 设置初始窗口大小
        self.root.geometry("1280x960")
        self.root.minsize(1000, 700)
        
        # 初始化变量
        self.pdf_path = None
        self.signature_path = None
        self.pdf_document = None
        self.current_page = 0
        self.pdf_image = None
        self.pdf_tk_image = None
        self.signature_image = None
        self.signature_tk_image = None
        self.signature_position = (50, 50)
        self.signature_width = 200
        self.signature_angle = 0  # 添加签名旋转角度初始值
        self.signatures = {}  # 保存各页面的签名信息 {页码: (位置, 大小, 角度)}
        self.watermark_enabled = True  # 默认启用防伪水印
        
        # 设置全局异常处理，避免未捕获的异常导致闪退
        def global_exception_handler(exc_type, exc_value, exc_traceback):
            import traceback
            error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            # 仅在非打包模式下打印错误
            if not getattr(sys, 'frozen', False):
                print(f"未捕获的异常: {error_msg}")
            try:
                messagebox.showerror("错误", f"程序发生错误: {str(exc_value)}\n请重新启动程序")
            except:
                pass

        sys.excepthook = global_exception_handler
        
        # 防伪标记相关变量
        self.watermark_enabled = True  # 是否启用防伪标记
        self.watermark_data = {}       # 存储签名防伪信息
        
        # 设置程序图标
        try:
            # 检查是否在PyInstaller环境中运行
            if getattr(sys, 'frozen', False):
                # 如果是打包后的exe，从资源文件中加载图标
                application_path = sys._MEIPASS
                icon_path = os.path.join(application_path, "signature.png")
            else:
                # 如果是脚本运行，从当前目录加载图标
                icon_path = "signature.png"
                
            # 创建图标对象并设置窗口图标
            icon_image = Image.open(icon_path)
            self._icon_photo = ImageTk.PhotoImage(icon_image)
            self.root.iconphoto(True, self._icon_photo)
            
        except Exception as e:
            self._icon_photo = None
            print(f"无法设置程序图标: {str(e)}")
        
        # 初始化变量
        self.pdf_path = None
        self.signature_path = None
        self.current_page = 0
        self.total_pages = 0
        self.pdf_image = None
        self.signature_image = None
        self.signature_tk_image = None
        self.signature_position = (0, 0)
        self.signature_dragging = False
        self.signature_width = 200
        # 用于存储多页签名信息的字典，格式为 {页码: (位置, 宽度)}
        self.signatures = {}
        # 缩放比例
        self.zoom_factor = 1.0
        # Adobe风格拖动相关参数
        self.drag_sensitivity = 1.0  # 基础灵敏度
        self.min_drag_distance = 1   # 最小响应拖动距离（像素）
        self.drag_acceleration = 1.1  # 拖动加速度因子
        self.drag_deceleration = 0.92  # 拖动减速度因子
        self.drag_velocity = [0, 0]    # 当前拖动速度 [x, y]
        self.drag_inertia = True       # 是否启用惯性滚动
        self.drag_momentum_timer = None  # 惯性滚动定时器
        self.last_drag_time = 0        # 上次拖动时间
        self.last_drag_pos = [0, 0]    # 上次拖动位置
        self.drag_speed_history = []   # 拖动速度历史
        self.max_speed_history = 5     # 最大速度历史记录数
        # 鼠标光标样式标志
        self.cursor_over_pdf = False    # 鼠标是否在PDF区域上方
        self.cursor_hand_active = False # 是否显示抓手光标
        # 记录上次窗口大小，用于判断是否需要重新适应大小
        self.last_window_width = 0
        self.last_window_height = 0
        # 临时文件列表，用于在关闭程序时清理
        self.temp_files = []
        # 缓存已转换的PDF页面
        self.page_cache = {}
        # 最大缓存页数
        self.max_cache_pages = 5
        
        # 参考A.py样式设置
        self.setup_new_style()
        
        # 创建界面
        self.create_widgets()
        
        # 绑定窗口大小改变事件
        self.root.bind("<Configure>", self.on_window_resize)
        
        # 绑定窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # 加载上次使用的签名路径
        self.load_last_signature_path()
        
        # 在所有初始化完成后，逐渐显示窗口
        if platform.system() == 'Windows':
            try:
                # 恢复窗口正常显示
                if getattr(sys, 'frozen', False):
                    self.root.attributes('-toolwindow', False)
                
                # 使用平滑动画显示窗口以减少视觉上的闪烁
                def fade_in():
                    current_alpha = self.root.attributes('-alpha')
                    if current_alpha < 1.0:
                        self.root.attributes('-alpha', min(current_alpha + 0.1, 1.0))
                        if current_alpha + 0.1 >= 1.0:
                            # 完全显示后，确保窗口在前台
                            self.root.lift()
                            self.root.attributes('-topmost', True)
                            self.root.update()
                            self.root.attributes('-topmost', False)
                        else:
                            self.root.after(5, fade_in)
                
                # 延迟100ms后开始显示窗口，确保UI已完全准备好
                self.root.after(100, fade_in)
                # 确保窗口显示
                self.root.deiconify()
            except:
                # 如果动画失败，直接显示窗口
                try:
                    self.root.deiconify()
                    self.root.attributes('-alpha', 1.0)
                except:
                    pass
    
    def setup_new_style(self):
        """根据A.py的风格调整按钮和字体样式"""
        # 颜色设置
        self.bg_color = "#f9f9f9"                  # 背景色
        self.panel_bg = "#f0f2f5"                  # 面板背景色
        self.accent_color = "#0078d4"              # 重点色(蓝色)
        self.text_color = "#202020"                # 文本颜色
        self.border_color = "#e0e0e0"              # 边框颜色
        self.hover_color = "#e6f2fa"               # 悬停颜色
        self.usage_instructions_color = "#808080"  # 使用说明颜色
        self.comment_color = "#808080"             # 注释颜色
        self.number_bg_color = "#2B7DE9"           # 步骤序号背景色 - 更友好的蓝色
        self.bullet_color = "#000000"              # 圆点颜色 - 黑色
        
        # 字体设置 - 设置为微软雅黑
        if sys.platform == "win32":
            # Windows系统使用微软雅黑
            self.font_family = "Microsoft YaHei"
        elif sys.platform == "darwin":
            # macOS优先使用苹方
            self.font_family = "PingFang SC"
        else:
            # Linux及其他系统使用通用字体
            self.font_family = "Noto Sans CJK SC"
        
        # 检查是否能正常加载指定字体，否则回退到系统默认字体
        try:
            test_label = tk.Label(self.root, font=(self.font_family, 10))
            test_label.destroy()
        except:
            # 回退到通用字体
            self.font_family = ""
            
        self.header_font = (self.font_family, 11, )   # 标题字体
        self.title_font = (self.font_family, 13, )    # 主标题字体
        self.normal_font = (self.font_family, 10)           # 正常文本字体
        self.small_font = (self.font_family, 9)             # 使用较小字体
        self.button_font = (self.font_family, 10)           # 按钮字体
        
        # 设置主题
        self.style = ttk.Style()
        
        # 根据不同操作系统选择合适的主题
        if sys.platform == "win32":
            self.style.theme_use('vista')  # Windows上使用vista主题
        elif sys.platform == "darwin":
            self.style.theme_use('aqua')   # macOS上使用aqua主题
        else:
            try:
                self.style.theme_use('clam')
            except:
                pass
                
        # 配置按钮样式 - 适当增加按钮填充以使其更美观
        self.style.configure('TButton', 
                            font=self.button_font,
                            background=self.bg_color,
                            foreground=self.text_color,
                            borderwidth=1,
                            relief="solid",
                            focusthickness=0,
                            padding=(10, 4))  # 调整按钮内边距
        
        # 强调按钮样式
        self.style.configure('Accent.TButton', 
                            font=self.button_font,
                            background=self.accent_color,
                            foreground='white',
                            borderwidth=1,
                            relief="solid",
                            focusthickness=0,
                            padding=(10, 4))  # 调整按钮内边距
                            
        # 调整按钮悬停和激活状态样式
        self.style.map('TButton',
                      foreground=[('active', self.accent_color)],
                      background=[('active', self.hover_color)],
                      relief=[('pressed', 'solid')],
                      borderwidth=[('pressed', 1)])
                      
        self.style.map('Accent.TButton',
                      foreground=[('active', 'white')],
                      background=[('active', '#005bb7')],
                      relief=[('pressed', 'solid')],
                      borderwidth=[('pressed', 1)])
        
        # 设置标签样式 - 调整标签内边距
        self.style.configure('TLabel', 
                            font=self.normal_font,
                            background=self.panel_bg,
                            foreground=self.text_color,
                            padding=3)  # 调整标签内边距
        
        # 设置标题标签样式
        self.style.configure('Header.TLabel', 
                            font=self.header_font,
                            background=self.panel_bg,
                            foreground=self.text_color,
                            padding=3)  # 调整标题内边距
        
        # 步骤序号标签样式 - 改为圆点样式
        self.style.configure('BulletPoint.TLabel',
                           font=(self.font_family, 14, 'bold'),
                           background=self.panel_bg,
                           foreground=self.bullet_color,
                           padding=(0, 0, 0, 0),
                           anchor=tk.CENTER)
        
        # 程序标题标签样式
        self.style.configure('Title.TLabel', 
                            font=self.title_font,
                            background=self.panel_bg,
                            foreground=self.text_color,
                            padding=3)  # 调整主标题内边距
        
        # 设置框架样式
        self.style.configure('Panel.TFrame', 
                            background=self.panel_bg,
                            borderwidth=0,
                            relief='flat')
                            
        # 设置输入框样式
        self.style.configure('TEntry',
                            font=self.normal_font, 
                            padding=4)  # 调整输入框内边距
                            
        # 设置组合框样式
        self.style.configure('TCombobox',
                            font=self.normal_font,
                            padding=3)  # 调整下拉框内边距
                            
        # 设置滑块样式
        self.style.configure('TScale',
                            background=self.panel_bg)
    
    def create_widgets(self):
        # 设置根窗口背景色
        self.root.configure(background=self.bg_color)
        
        # 添加根窗口的行列权重配置，使其可以根据窗口调整大小
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=0)  # 右侧面板不需要调整大小
        
        # 右侧面板 - 控制和选项
        right_panel = ttk.Frame(self.root, style='Panel.TFrame', width=310)  # 调整面板宽度
        right_panel.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)  # 修改为nsew以充分填充
        
        # 确保右侧面板可以垂直拉伸
        right_panel.grid_propagate(False)  # 防止panel被内容撑开
        right_panel.pack_propagate(False)  # 防止pack影响panel大小
        
        # 移除Canvas和滚动条相关代码，直接使用一个框架
        right_container = ttk.Frame(right_panel, style='Panel.TFrame')
        right_container.pack(fill=tk.BOTH, expand=True)
        
        # 添加面板标题
        title_frame = ttk.Frame(right_container, style='Panel.TFrame')
        title_frame.pack(fill=tk.X, pady=(6, 10))  # 减少顶部边距
        ttk.Label(title_frame, text="欢迎使用", style='Title.TLabel').pack(anchor=tk.CENTER)
        
        # PDF文件选择 - 放在同一行
        step1_frame = ttk.Frame(right_container, style='Panel.TFrame')
        step1_frame.pack(fill=tk.X, pady=(0, 2), padx=10)  # 减少垂直间距
        
        # 使用圆点样式的标签
        ttk.Label(step1_frame, text="•", style='BulletPoint.TLabel').pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(step1_frame, text="选择PDF文件", style='Header.TLabel').pack(side=tk.LEFT, anchor=tk.W)
        pdf_button = ttk.Button(step1_frame, text="选择文件", style='TButton', command=self.select_pdf)
        pdf_button.pack(side=tk.RIGHT)
        
        # 文件信息框
        file_info_frame = ttk.Frame(right_container, style='Panel.TFrame')
        file_info_frame.pack(fill=tk.X, pady=(0, 8), padx=10)  # 减少垂直间距
        self.pdf_label = ttk.Label(file_info_frame, text="未选择PDF", wraplength=270)
        self.pdf_label.pack(fill=tk.X, pady=2, padx=5)  # 减少内部垂直边距
        
        # 签名图片选择 - 放在同一行
        step2_frame = ttk.Frame(right_container, style='Panel.TFrame')
        step2_frame.pack(fill=tk.X, pady=(0, 2), padx=10)  # 减少垂直间距
        
        # 使用圆点样式的标签
        ttk.Label(step2_frame, text="•", style='BulletPoint.TLabel').pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(step2_frame, text="选择签名图片", style='Header.TLabel').pack(side=tk.LEFT, anchor=tk.W)
        signature_button = ttk.Button(step2_frame, text="选择图片", style='TButton', command=self.select_signature)
        signature_button.pack(side=tk.RIGHT)
        
        # 签名信息框
        sig_info_frame = ttk.Frame(right_container, style='Panel.TFrame')
        sig_info_frame.pack(fill=tk.X, pady=(0, 8), padx=10)  # 减少垂直间距
        self.signature_label = ttk.Label(sig_info_frame, text="未选择签名", wraplength=270)
        self.signature_label.pack(fill=tk.X, pady=2, padx=5)  # 减少内部垂直边距
        
        # 签名大小调整 - 放在同一行
        step3_frame = ttk.Frame(right_container, style='Panel.TFrame')
        step3_frame.pack(fill=tk.X, pady=(0, 2), padx=10)  # 减少垂直间距
        
        # 使用圆点样式的标签
        ttk.Label(step3_frame, text="•", style='BulletPoint.TLabel').pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(step3_frame, text="调整签名大小", style='Header.TLabel').pack(side=tk.LEFT, anchor=tk.W)
        
        # 大小调整滑块
        size_frame = ttk.Frame(right_container, style='Panel.TFrame')
        size_frame.pack(fill=tk.X, pady=(0, 6), padx=10)  # 减少垂直间距
        
        ttk.Label(size_frame, text="宽度: ").pack(side=tk.LEFT)
        
        # 使用ttk.Scale代替tk.Scale以获得更现代的外观
        self.size_scale = ttk.Scale(size_frame, from_=50, to=500, orient=tk.HORIZONTAL, 
                                   command=self.update_signature_size, length=180)
        self.size_scale.set(self.signature_width)
        self.size_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        
        # 显示当前值的标签
        self.size_value_label = ttk.Label(size_frame, text=f"{self.signature_width}px")
        self.size_value_label.pack(side=tk.RIGHT, padx=4)
        
        # 添加签名角度调整控件
        angle_frame = ttk.Frame(right_container, style='Panel.TFrame')
        angle_frame.pack(fill=tk.X, pady=(0, 6), padx=10)  # 减少垂直间距
        
        ttk.Label(angle_frame, text="旋转: ").pack(side=tk.LEFT)
        
        # 角度调整滑块
        self.angle_scale = ttk.Scale(angle_frame, from_=0, to=359, orient=tk.HORIZONTAL, 
                                    command=self.update_signature_angle, length=180)
        self.angle_scale.set(self.signature_angle)
        self.angle_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        
        # 显示当前角度值的标签
        self.angle_value_label = ttk.Label(angle_frame, text=f"{self.signature_angle}°")
        self.angle_value_label.pack(side=tk.RIGHT, padx=4)
        
        # 快速角度按钮框架 - 调整间距
        angle_buttons_frame = ttk.Frame(right_container, style='Panel.TFrame')
        angle_buttons_frame.pack(fill=tk.X, pady=(0, 10), padx=10)  # 减少底部间距
        
        # 添加快速角度按钮
        btn_width = 5  # 缩小按钮宽度，确保所有按钮都能显示
        ttk.Button(angle_buttons_frame, text="0°", style='TButton', width=btn_width,
                 command=lambda: self.set_signature_angle(0)).pack(side=tk.LEFT, padx=1, fill=tk.X, expand=True)
        ttk.Button(angle_buttons_frame, text="90°", style='TButton', width=btn_width,
                 command=lambda: self.set_signature_angle(90)).pack(side=tk.LEFT, padx=1, fill=tk.X, expand=True)
        ttk.Button(angle_buttons_frame, text="180°", style='TButton', width=btn_width,
                 command=lambda: self.set_signature_angle(180)).pack(side=tk.LEFT, padx=1, fill=tk.X, expand=True)
        ttk.Button(angle_buttons_frame, text="270°", style='TButton', width=btn_width,
                 command=lambda: self.set_signature_angle(270)).pack(side=tk.LEFT, padx=1, fill=tk.X, expand=True)
        
        # 页面导航和管理 - 放在同一行
        step4_frame = ttk.Frame(right_container, style='Panel.TFrame')
        step4_frame.pack(fill=tk.X, pady=(0, 2), padx=10)  # 减少垂直间距
        
        # 使用圆点样式的标签
        ttk.Label(step4_frame, text="•", style='BulletPoint.TLabel').pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(step4_frame, text="页面管理", style='Header.TLabel').pack(side=tk.LEFT, anchor=tk.W)
        
        # 页面导航 - 使用更舒适的布局
        nav_frame = ttk.Frame(right_container, style='Panel.TFrame')
        nav_frame.pack(fill=tk.X, pady=(0, 4), padx=10)  # 减少垂直间距
        
        self.prev_button = ttk.Button(nav_frame, text="上一页", style='TButton', command=self.previous_page, state=tk.DISABLED)
        self.prev_button.pack(side=tk.LEFT, padx=(0, 4))
        
        self.page_label = ttk.Label(nav_frame, text="0 / 0", width=8, anchor=tk.CENTER)
        self.page_label.pack(side=tk.LEFT, padx=4, expand=True)
        
        self.next_button = ttk.Button(nav_frame, text="下一页", style='TButton', command=self.next_page, state=tk.DISABLED)
        self.next_button.pack(side=tk.RIGHT, padx=(4, 0))
        
        # 直接页面跳转 - 更舒适的布局
        jump_frame = ttk.Frame(right_container, style='Panel.TFrame')
        jump_frame.pack(fill=tk.X, pady=(0, 4), padx=10)  # 减少垂直间距
        
        ttk.Label(jump_frame, text="跳转到页: ").pack(side=tk.LEFT)
        self.page_entry = ttk.Combobox(jump_frame, width=5, state="readonly")  # 保持宽度
        self.page_entry.pack(side=tk.LEFT, padx=4)
        self.page_entry.bind("<<ComboboxSelected>>", self.jump_to_page)
        
        # 签名管理 - 使用更舒适的布局
        sign_mgmt_frame = ttk.Frame(right_container, style='Panel.TFrame')
        sign_mgmt_frame.pack(fill=tk.X, pady=(0, 8), padx=10)  # 减少间距
        
        self.add_sign_button = ttk.Button(sign_mgmt_frame, text="添加签名到当前页", style='TButton',
                                     command=self.add_signature_to_page, state=tk.DISABLED)
        self.add_sign_button.pack(side=tk.LEFT, padx=(0, 6), fill=tk.X, expand=True)
        
        self.remove_sign_button = ttk.Button(sign_mgmt_frame, text="移除当前页签名", style='TButton',
                                       command=self.remove_signature_from_page, state=tk.DISABLED)
        self.remove_sign_button.pack(side=tk.RIGHT, padx=(6, 0), fill=tk.X, expand=True)
        
        # 已添加签名页面列表 - 更舒适的布局
        signed_label_frame = ttk.Frame(right_container, style='Panel.TFrame')
        signed_label_frame.pack(fill=tk.X, pady=(0, 2), padx=10)  # 减少垂直间距
        ttk.Label(signed_label_frame, text="已添加签名的页面:", font=self.normal_font).pack(anchor=tk.W)
        
        # 创建带边框的容器
        listbox_container = tk.Frame(right_container, bg=self.border_color, bd=1, relief=tk.SOLID)
        listbox_container.pack(fill=tk.X, pady=(0, 8), padx=10)  # 减少下方间距
        
        # 现代风格的Listbox - 增加高度以显示更多签名页面
        self.signed_pages_listbox = tk.Listbox(listbox_container, height=5, font=self.small_font,
                                       bg=self.bg_color, fg=self.text_color, 
                                       bd=0, highlightthickness=0,
                                       selectbackground=self.accent_color, selectforeground="white")
        self.signed_pages_listbox.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        self.signed_pages_listbox.bind('<<ListboxSelect>>', self.on_signed_page_selected)
        
        # 保存按钮 - 更舒适的布局
        step5_frame = ttk.Frame(right_container, style='Panel.TFrame')
        step5_frame.pack(fill=tk.X, pady=(0, 2), padx=10)  # 减少垂直间距
        
        # 使用圆点样式的标签
        ttk.Label(step5_frame, text="•", style='BulletPoint.TLabel').pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(step5_frame, text="保存签名文件", style='Header.TLabel').pack(side=tk.LEFT, anchor=tk.W)
        
        self.save_button = ttk.Button(step5_frame, text="保存", style='TButton', 
                                 command=self.save_pdf)
        self.save_button.pack(side=tk.RIGHT)
        
        # 添加防伪验证功能 - 新增
        verify_frame = ttk.Frame(right_container, style='Panel.TFrame')
        verify_frame.pack(fill=tk.X, pady=(10, 2), padx=10)  # 减少垂直间距
        
        # 使用圆点样式的标签
        ttk.Label(verify_frame, text="•", style='BulletPoint.TLabel').pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(verify_frame, text="防伪验证", style='Header.TLabel').pack(side=tk.LEFT, anchor=tk.W)
        
        #verify_btn_frame = ttk.Frame(right_container, style='Panel.TFrame')
        #verify_btn_frame.pack(fill=tk.X, pady=(0, 8), padx=10)
        ttk.Button(verify_frame, text="验证文件", style='TButton',
                  command=self.verify_signature).pack(side=tk.RIGHT)
        
        # 防伪设置
        watermark_frame = ttk.Frame(right_container, style='Panel.TFrame')
        watermark_frame.pack(fill=tk.X, pady=(0, 8), padx=10)  # 减少垂直间距
        
        # 创建Checkbutton变量
        self.watermark_var = tk.BooleanVar(value=self.watermark_enabled)
        
        # 添加Checkbutton控件
        watermark_check = ttk.Checkbutton(watermark_frame, text="添加防伪标记",
                                      variable=self.watermark_var,
                                      command=self.toggle_watermark)
        watermark_check.pack(side=tk.LEFT)
        
        # 添加水平分割线
        separator_frame = ttk.Frame(right_container, height=1, style='Panel.TFrame')
        separator_frame.pack(fill=tk.X, pady=(5, 5), padx=10)
        ttk.Separator(separator_frame, orient=tk.HORIZONTAL).pack(fill=tk.X)
        
        # 帮助信息区域
        help_frame = ttk.Frame(right_container, style='Panel.TFrame', padding=1)
        help_frame.pack(fill=tk.X, pady=(0, 5), padx=10)
        
        help_text = "使用说明:\n" \
                    "            1. 选择要添加签名的PDF文件\n" \
                    "            2. 选择签名图片\n" \
                    "            3. 调整签名大小和旋转角度\n" \
                    "            4. 选择页面添加签名\n" \
                    "            5. 调整签名位置\n" \
                    "            6. 保存签名后的PDF\n" \
                    "            7. 防伪验证可检查签名文件是否被修改\n" \
                    "提示: 按住Ctrl+滚轮缩放，点击拖动移动页面\n" \
                    "        可使用角度滑块或快捷按钮旋转签名"
        
        ttk.Label(help_frame, text=help_text, font=self.small_font, 
              justify=tk.LEFT, wraplength=280, foreground=self.usage_instructions_color).pack(anchor=tk.W)
        
        # 底部空白区域，确保有足够的滚动空间
        bottom_spacer = ttk.Frame(right_container, style='Panel.TFrame', height=20)
        bottom_spacer.pack(fill=tk.X)
        
        # 左侧面板 - PDF预览 (圆角边框)
        self.preview_frame = ttk.Frame(self.root, padding=2)
        self.preview_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        # 配置预览框架的行列权重，使其内容可以跟随调整
        self.preview_frame.columnconfigure(0, weight=1)
        self.preview_frame.rowconfigure(0, weight=1)
        
        # 内部容器 - 用于圆角和阴影效果
        preview_inner = ttk.Frame(self.preview_frame, style='Panel.TFrame')
        preview_inner.grid(row=0, column=0, sticky="nsew")
        
        # 配置内部预览的行列权重
        preview_inner.columnconfigure(0, weight=1)
        preview_inner.rowconfigure(0, weight=1)
        
        # 创建滚动条 - 使用ttk风格
        self.v_scrollbar = ttk.Scrollbar(preview_inner, orient=tk.VERTICAL)
        self.v_scrollbar.grid(row=0, column=1, sticky="ns")
        
        self.h_scrollbar = ttk.Scrollbar(preview_inner, orient=tk.HORIZONTAL)
        self.h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        # 添加PDF控制面板到预览区域底部
        self.pdf_control_frame = ttk.Frame(preview_inner, padding=5)
        self.pdf_control_frame.grid(row=2, column=0, sticky="ew")
        
        # 缩放控制 - 移动到左侧PDF预览底部居中
        zoom_frame = ttk.Frame(self.pdf_control_frame, style='Panel.TFrame')
        zoom_frame.pack(side=tk.TOP, pady=5, fill=tk.X)
        
        # 创建一个内部容器来承载按钮，并使其居中
        zoom_container = ttk.Frame(zoom_frame, style='Panel.TFrame')
        zoom_container.pack(side=tk.TOP, anchor=tk.CENTER, expand=True)
        
        zoom_out_btn = ttk.Button(zoom_container, text="-", style='TButton',
                             command=self.zoom_out, width=2)
        zoom_out_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.zoom_label = ttk.Label(zoom_container, text="100%", width=6, anchor=tk.CENTER)
        self.zoom_label.pack(side=tk.LEFT, padx=5)
        
        zoom_in_btn = ttk.Button(zoom_container, text="+", style='TButton',
                            command=self.zoom_in, width=2)
        zoom_in_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        fit_btn = ttk.Button(zoom_container, text="适合页面", style='TButton',
                        command=self.fit_to_page)
        fit_btn.pack(side=tk.LEFT, padx=(15, 0))
        
        # 创建带滚动条的画布 - 使用纯白背景
        self.canvas_bg = "#999999"  # 设置统一的画布背景颜色
        self.canvas = tk.Canvas(
            preview_inner, 
            bg=self.canvas_bg, 
            highlightthickness=0,
            xscrollcommand=self.h_scrollbar.set,
            yscrollcommand=self.v_scrollbar.set
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        
        # 配置滚动条
        self.h_scrollbar.config(command=self.canvas.xview)
        self.v_scrollbar.config(command=self.canvas.yview)
        
        # 绑定鼠标滚轮事件
        self.canvas.bind("<MouseWheel>", self.on_mousewheel)  # Windows
        self.canvas.bind("<Button-4>", self.on_mousewheel)    # Linux上滚
        self.canvas.bind("<Button-5>", self.on_mousewheel)    # Linux下滚
        
        # 绑定拖动事件
        self.canvas.bind("<Button-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.stop_drag)
        
        # 添加鼠标悬停事件
        self.canvas.bind("<Enter>", self.on_mouse_enter)
        self.canvas.bind("<Leave>", self.on_mouse_leave)
        
        # 跟踪页面拖动状态
        self.page_dragging = False
        
        # 跟踪键盘修饰键状态
        self.ctrl_pressed = False
        self.root.bind("<KeyPress-Control_L>", self.ctrl_press)
        self.root.bind("<KeyPress-Control_R>", self.ctrl_press)
        self.root.bind("<KeyRelease-Control_L>", self.ctrl_release)
        self.root.bind("<KeyRelease-Control_R>", self.ctrl_release)
        
        # 初始化计时器变量
        self.resize_timer = None
    
    def toggle_watermark(self):
        """切换防伪标记启用状态"""
        self.watermark_enabled = self.watermark_var.get()
        
    def verify_signature(self):
        """验证PDF签名防伪标记"""
        file_path = filedialog.askopenfilename(
            title="选择需要验证的PDF文件",
            filetypes=[("PDF文件", "*.pdf")]
        )
        if not file_path:
            return
            
        try:
            # 验证PDF防伪标记
            success, result = self.verify_pdf_watermark(file_path)
            
            if success:
                # 验证成功，显示详细信息
                info_text = "验证结果: 已通过\n"
                info_text += f"签名ID: {result.get('签名ID', '未知')}\n"
                info_text += f"签名时间: {result.get('签名时间', '未知')}\n"
                info_text += f"签名页数: {result.get('签名页面', 0)} 页\n"
                info_text += f"签名软件: {result.get('签名软件', '未知')}\n"
                info_text += "是否本机签名: 是\n"
                
                # 添加计算机信息
                computer_info = result.get('计算机信息', {})
                if computer_info:
                    info_text += "=== 签名设备信息 ===\n"
                    for key, value in computer_info.items():
                        info_text += f"{key}: {value}\n"
                
                # 创建一个滚动文本窗口来显示详细信息
                self.show_verification_details(info_text, True)
            else:
                # 验证失败，但如果是计算机信息不匹配，仍然显示详情
                if isinstance(result, str) and "计算机信息不匹配" in result:
                    # 提取原始数据中的计算机信息
                    watermark_data = self.extract_watermark_from_pdf(file_path)
                    if watermark_data and "computer_info" in watermark_data:
                        # 构建详细信息显示
                        info_text = "验证结果: 未通过\n"
                        info_text += f"签名ID: {watermark_data.get('signature_id', '未知')}\n"
                        info_text += f"签名时间: {watermark_data.get('timestamp', '未知')}\n"
                        info_text += f"签名页数: {len(watermark_data.get('pages_info', {}))} 页\n"
                        info_text += f"签名软件: {watermark_data.get('software', '未知')}\n"
                        info_text += "是否本机签名: 否\n"
                        
                        # 添加计算机信息
                        computer_info = watermark_data.get('computer_info', {})
                        if computer_info:
                            info_text += "=== 签名设备信息 ===\n"
                            for key, value in computer_info.items():
                                info_text += f"{key}: {value}\n"
                                
                        # 显示当前计算机信息，用于对比
                        current_info = self.get_computer_info()
                        if current_info:
                            info_text += "\n=== 当前计算机信息 ===\n"
                            for key, value in current_info.items():
                                info_text += f"{key}: {value}\n"
                                
                        # 创建一个滚动文本窗口来显示详细信息，标记为验证失败
                        self.show_verification_details(info_text, False, "计算机信息不匹配")
                        
                        # 额外提示信息
                        messagebox.showinfo("防伪验证结果", 
                            "验证失败: 计算机信息不匹配\n\n"
                            "此PDF文件不是在本计算机上签名的，无法通过验证。\n"
                            "防伪验证要求在签名PDF的原始计算机上验证才能通过。")
                    else:
                        # 没有找到完整的计算机信息
                        messagebox.showinfo("防伪验证结果", 
                            "验证失败: 计算机信息不匹配\n\n"
                            "此PDF文件不是在本计算机上签名的，无法通过验证。")
                elif isinstance(result, str) and "未找到防伪标记" in result:
                    # 没有防伪标记
                    messagebox.showinfo("防伪验证结果", 
                        "验证失败: 未找到防伪标记\n\n"
                        "此PDF文件可能不是由本程序签名的，或者签名时未启用防伪标记功能。")
                else:
                    # 其他失败原因
                    messagebox.showinfo("防伪验证结果", 
                        f"验证失败: {result}\n\n"
                        "此PDF文件可能被修改或损坏，无法验证其真实性。")
        except Exception as e:
            messagebox.showerror("验证错误", f"验证过程中出错: {str(e)}")
    
    def show_verification_details(self, info_text, is_verified=True, fail_reason=""):
        """显示验证详细信息的对话框"""
        details_window = tk.Toplevel(self.root)
        details_window.title("PDF文件防伪验证")
        details_window.geometry("450x430")  # 增加窗口高度确保显示关闭按钮
        details_window.resizable(False, False)  # 设置为不可调整大小
        details_window.transient(self.root)
        details_window.grab_set()
        
        # 设置窗口图标与主窗口相同
        try:
            if hasattr(self.root, '_icon_photo'):
                details_window.iconphoto(False, self.root._icon_photo)
        except:
            pass
        
        # 使窗口居中显示
        self.center_window(details_window)
            
        # 创建标题
        ttk.Label(details_window, text="验证详情", 
                  font=(self.font_family, 13, "bold")).pack(pady=(10, 5))
        
        # 判断是否为本机签名
        is_local_machine = False
        lines = info_text.split('\n')
        
        # 检查是否本机签名
        for line in lines:
            if "是否本机签名: 是" in line:
                is_local_machine = True
                break
        
        # 创建一个顶部结果区域框架，用于更好地控制布局
        result_frame = ttk.Frame(details_window)
        result_frame.pack(fill=tk.X, padx=15)
        
        # 验证结果标签
        if is_verified:
            result_label = ttk.Label(result_frame, text="验证结果: 已通过", 
                                   font=(self.font_family, 11, "bold"))
            result_label.pack(side=tk.LEFT, pady=2)
            
            # 添加"本机签名"标签，使用绿色文本
            local_label = ttk.Label(result_frame, text="本机签名", 
                                  font=(self.font_family, 10, "bold"),
                                  foreground="#008800")
            local_label.pack(side=tk.RIGHT, pady=2)
        else:
            result_label = ttk.Label(result_frame, text="验证结果: 未通过", 
                                   font=(self.font_family, 11, "bold"),
                                   foreground="#cc0000")
            result_label.pack(side=tk.LEFT, pady=2)
            
            # 添加"非本机签名"标签，使用红色文本
            non_local_label = ttk.Label(result_frame, text="非本机签名", 
                                      font=(self.font_family, 10, "bold"),
                                      foreground="#cc0000")
            non_local_label.pack(side=tk.RIGHT, pady=2)
        
        # 创建主容器框架
        main_container = ttk.Frame(details_window)
        main_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=2)
        
        # 创建内容框架，使用固定大小的框架
        content_frame = ttk.Frame(main_container)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建文本显示区域，没有滚动条
        text_widget = tk.Text(content_frame, 
                             font=(self.font_family, 10),
                             wrap=tk.WORD,
                             bd=1,
                             relief=tk.SOLID,
                             height=14,  # 调整文本区域高度
                             width=48)
        text_widget.pack(fill=tk.BOTH, expand=True)
        
        # 禁用鼠标滚轮和按键滚动
        def block_scroll(event):
            return "break"
            
        text_widget.bind("<MouseWheel>", block_scroll)  # Windows
        text_widget.bind("<Button-4>", block_scroll)    # Linux上滚
        text_widget.bind("<Button-5>", block_scroll)    # Linux下滚
        text_widget.bind("<Up>", block_scroll)          # 上箭头键
        text_widget.bind("<Down>", block_scroll)        # 下箭头键
        text_widget.bind("<Prior>", block_scroll)       # Page Up
        text_widget.bind("<Next>", block_scroll)        # Page Down
        
        # 添加文本标签和颜色
        text_widget.tag_configure("green", foreground="#008800", font=(self.font_family, 10, "bold"))
        text_widget.tag_configure("red", foreground="#cc0000", font=(self.font_family, 10, "bold"))
        text_widget.tag_configure("bold", font=(self.font_family, 10, "bold"))
        text_widget.tag_configure("title", font=(self.font_family, 11, "bold"))
        
        # 删除验证结果行，因为已经在顶部显示
        # 提取有效信息行
        valid_lines = []
        for line in lines:
            if line and not line.startswith("验证结果:"):
                valid_lines.append(line)
        
        # 添加计算机匹配状态提示
        text_widget.insert(tk.END, "计算机信息: ", "bold")
        if is_verified:
            text_widget.insert(tk.END, "完全匹配", "green")
        else:
            text_widget.insert(tk.END, "不匹配", "red")
            if fail_reason:
                text_widget.insert(tk.END, f" - {fail_reason}", "red")
        text_widget.insert(tk.END, "\n\n")
        
        # 遍历所有行并显示在文本框中
        for line in valid_lines:
            if "签名ID:" in line:
                # 将签名ID显示为普通文本，不使用背景
                text_widget.insert(tk.END, line + "\n")
            elif "是否本机签名:" in line:
                # 显示是否本机签名
                text_widget.insert(tk.END, "是否本机签名: ", "bold")
                if is_verified:
                    text_widget.insert(tk.END, "是", "green")
                else:
                    text_widget.insert(tk.END, "否", "red")
                text_widget.insert(tk.END, "\n")
            elif "=== 签名设备信息 ===" in line or "=== 当前计算机信息 ===" in line:
                text_widget.insert(tk.END, "\n" + line + "\n", "bold")
            else:
                text_widget.insert(tk.END, line + "\n")
        
        # 设置为只读
        text_widget.config(state=tk.DISABLED)
        
        # 创建按钮框架
        button_frame = ttk.Frame(details_window)
        button_frame.pack(fill=tk.X, pady=10)
        
        # 添加关闭按钮
        ttk.Button(button_frame, text="关闭", 
                  command=details_window.destroy,
                  width=10).pack()
    
    def center_window(self, window):
        """使窗口居中显示在主窗口中央"""
        window.update_idletasks()
        
        # 获取主窗口和弹窗的尺寸
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        main_x = self.root.winfo_rootx()
        main_y = self.root.winfo_rooty()
        
        window_width = window.winfo_width()
        window_height = window.winfo_height()
        
        # 计算居中位置
        x = main_x + (main_width - window_width) // 2
        y = main_y + (main_height - window_height) // 2
        
        # 确保窗口不会超出屏幕
        if x < 0:
            x = 0
        if y < 0:
            y = 0
            
        # 设置窗口位置
        window.geometry(f"+{x}+{y}")
    
    def ctrl_press(self, event):
        self.ctrl_pressed = True
        
    def ctrl_release(self, event):
        self.ctrl_pressed = False
    
    def on_mousewheel(self, event):
        # 如果按住Ctrl键，执行缩放操作
        if self.ctrl_pressed:
            if event.num == 5 or event.delta < 0:  # 向下滚动 - 缩小
                self.zoom_out()
            elif event.num == 4 or event.delta > 0:  # 向上滚动 - 放大
                self.zoom_in()
        else:
            # 普通滚动 - 垂直滚动PDF
            if event.num == 5 or event.delta < 0:  # 向下滚动
                self.canvas.yview_scroll(1, "units")
            elif event.num == 4 or event.delta > 0:  # 向上滚动
                self.canvas.yview_scroll(-1, "units")
    
    def zoom_in(self):
        if self.pdf_image:
            self.zoom_factor *= 1.2
            self.update_zoom()
    
    def zoom_out(self):
        if self.pdf_image:
            self.zoom_factor /= 1.2
            if self.zoom_factor < 0.1:  # 设置最小缩放限制
                self.zoom_factor = 0.1
            self.update_zoom()
    
    def fit_to_page(self):
        if not self.pdf_image:
            return
            
        # 获取预览框的尺寸
        frame_width = self.preview_frame.winfo_width() - self.v_scrollbar.winfo_width() - 10
        frame_height = self.preview_frame.winfo_height() - self.h_scrollbar.winfo_height() - 10
        
        # 确保测量值有效
        if frame_width < 50 or frame_height < 50:
            # 等待布局完成后再试
            self.root.after(100, self.fit_to_page)
            return
        
        # 计算适合预览框的缩放因子
        width_ratio = frame_width / self.pdf_image.width
        height_ratio = frame_height / self.pdf_image.height
        
        # 选择较小的缩放比例，确保整个页面都可见
        self.zoom_factor = min(width_ratio, height_ratio) * 0.95
        
        self.update_zoom()
    
    def update_zoom(self):
        # 更新缩放标签
        self.zoom_label.config(text=f"{int(self.zoom_factor * 100)}%")
        
        if not self.pdf_image:
            return
        
        # 应用缩放
        width = int(self.pdf_image.width * self.zoom_factor)
        height = int(self.pdf_image.height * self.zoom_factor)
        
        # 调整后的图像
        if self.zoom_factor == 1.0:
            resized_image = self.pdf_image
        else:
            resized_image = self.pdf_image.resize((width, height), Image.LANCZOS)
        
        self.pdf_tk_image = ImageTk.PhotoImage(resized_image)
        
        # 清除画布并重新绘制PDF
        self.canvas.delete("all")
        
        # 计算画布可见区域的大小
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        # 设置完整滚动区域，确保足够大以填充整个视图或容纳PDF，以较大者为准
        padding_x = max(20, (canvas_width - width) // 2)
        padding_y = max(20, (canvas_height - height) // 2)
        
        # 确保滚动区域始终至少与画布一样大
        scroll_width = max(canvas_width, width + padding_x * 2)
        scroll_height = max(canvas_height, height + padding_y * 2)
        
        # 设置滚动区域
        self.canvas.config(scrollregion=(0, 0, scroll_width, scroll_height))
        
        # 绘制全屏灰色背景，确保覆盖整个滚动区域
        self.canvas.create_rectangle(0, 0, scroll_width, scroll_height, 
                                    fill=self.canvas_bg, outline=self.canvas_bg, tags="bg")
        
        # 居中显示PDF
        pdf_x = padding_x
        pdf_y = padding_y
        self.canvas.create_image(pdf_x, pdf_y, anchor=tk.NW, image=self.pdf_tk_image, tags="pdf")
        
        # 如果当前页有签名，重新显示签名
        if self.current_page in self.signatures and self.signature_image:
            self.update_signature(padding_x, padding_y)
    
    def select_pdf(self):
        file_path = filedialog.askopenfilename(
            title="选择PDF文件",
            filetypes=[("PDF文件", "*.pdf")]
        )
        if file_path:
            self.pdf_path = file_path
            self.pdf_label.config(text=os.path.basename(file_path))
            
            # 重置缩放因子
            self.zoom_factor = 1.0
            self.zoom_label.config(text="100%")
            
            # 清空已有的签名信息
            self.signatures = {}
            self.update_signed_pages_list()
            
            # 显示加载中的信息
            self.page_label.config(text="加载中...")
            self.root.configure(cursor="wait")
            
            # 在左侧PDF预览区域显示明显的加载提示
            self.canvas.delete("all")
            
            # 获取预览区域大小
            canvas_width = self.canvas.winfo_width() or 800
            canvas_height = self.canvas.winfo_height() or 600
            
            # 创建一个大的灰色背景
            self.canvas.create_rectangle(0, 0, canvas_width, canvas_height, 
                                       fill=self.canvas_bg, outline=self.canvas_bg)
            
            # 在中央显示加载提示文本
            self.canvas.create_text(
                canvas_width // 2 or 400, 
                canvas_height // 2 - 50 or 250,
                text="PDF文件加载中...",
                font=(self.font_family, 16, "bold"),
                fill="#333333"
            )
            
            # 创建一个提示说明，如果文件较大可能需要更长时间
            self.canvas.create_text(
                canvas_width // 2 or 400, 
                canvas_height // 2 or 300,
                text="如果文件较大，加载可能需要一些时间\n请耐心等待",
                font=(self.font_family, 12),
                fill="#555555",
                justify=tk.CENTER
            )
            
            # 创建一个进度指示
            self.loading_progress = 0
            self.loading_indicator = self.canvas.create_rectangle(
                canvas_width // 2 - 100 or 300, 
                canvas_height // 2 + 50 or 350,
                canvas_width // 2 - 100 or 300, 
                canvas_height // 2 + 70 or 370,
                fill=self.accent_color, 
                outline=self.accent_color
            )
            
            # 开始进度动画
            self.animate_loading_progress()
            
            # 立即更新画布以显示加载中提示
            self.root.update()
            
            # 清空页面缓存
            self.page_cache = {}
            
            # 加载PDF
            try:
                # 使用后台线程加载PDF
                import threading
                
                def load_pdf_task():
                    try:
                        self.pdf_reader = PdfReader(self.pdf_path)
                        self.total_pages = len(self.pdf_reader.pages)
                        self.current_page = 0
                        
                        # 初始化pdf_document变量
                        self.pdf_document = self.pdf_reader
                        
                        # 停止加载动画定时器
                        if hasattr(self, 'loading_timer') and self.loading_timer:
                            self.root.after_cancel(self.loading_timer)
                            self.loading_timer = None
                        
                        # 在主线程中更新UI
                        self.root.after(0, self.update_pdf_ui)
                    except Exception as e:
                        # 停止加载动画定时器
                        if hasattr(self, 'loading_timer') and self.loading_timer:
                            self.root.after_cancel(self.loading_timer)
                            self.loading_timer = None
                            
                        # 在主线程中显示错误
                        self.root.after(0, lambda: self.show_error(f"无法打开PDF文件: {str(e)}"))
                
                # 启动后台线程，不显示命令行窗口
                thread = threading.Thread(target=load_pdf_task, daemon=True)
                thread.name = "PDF加载线程"  # 设置线程名称，便于调试
                thread.start()
                
            except Exception as e:
                # 停止加载动画定时器
                if hasattr(self, 'loading_timer') and self.loading_timer:
                    self.root.after_cancel(self.loading_timer)
                    self.loading_timer = None
                    
                messagebox.showerror("错误", f"无法打开PDF文件: {str(e)}")
                self.root.configure(cursor="")
    
    def animate_loading_progress(self):
        """创建加载动画效果"""
        # 获取预览区域大小
        canvas_width = self.canvas.winfo_width() or 800
        
        # 更新进度条位置
        self.loading_progress += 0.05
        if self.loading_progress > 1:
            self.loading_progress = 0
        
        # 确保loading_indicator存在且有效
        if hasattr(self, 'loading_indicator') and self.canvas.winfo_exists():
            try:
                coords = self.canvas.coords(self.loading_indicator)
                if coords and len(coords) >= 4:  # 确保坐标列表完整
                    # 更新进度指示器位置
                    self.canvas.coords(
                        self.loading_indicator,
                        coords[0],
                        coords[1],
                        coords[0] + self.loading_progress * 200,  # 根据百分比调整宽度
                        coords[3]
                    )
            except Exception:
                pass  # 忽略可能的错误
        
        # 每40毫秒更新一次，实现平滑动画
        self.loading_timer = self.root.after(40, self.animate_loading_progress)
    
    def show_error(self, message):
        """显示错误信息并恢复光标"""
        # 停止加载动画定时器
        if hasattr(self, 'loading_timer') and self.loading_timer:
            self.root.after_cancel(self.loading_timer)
            self.loading_timer = None
            
        messagebox.showerror("错误", message)
        self.root.configure(cursor="")
        self.page_label.config(text="0 / 0")
    
    def update_pdf_ui(self):
        """更新PDF加载后的UI元素"""
        self.page_label.config(text=f"{self.current_page + 1} / {self.total_pages}")
        
        # 更新页面跳转下拉框
        page_numbers = [str(i + 1) for i in range(self.total_pages)]
        self.page_entry['values'] = page_numbers
        if len(page_numbers) > 0:
            self.page_entry.current(0)
        
        # 启用导航按钮
        self.prev_button.config(state=tk.NORMAL if self.current_page > 0 else tk.DISABLED)
        self.next_button.config(state=tk.NORMAL if self.current_page < self.total_pages - 1 else tk.DISABLED)
        self.add_sign_button.config(state=tk.NORMAL if self.signature_path else tk.DISABLED)
        
        # 确保pdf_document变量已初始化
        self.pdf_document = self.pdf_reader
        
        # 显示第一页
        self.display_pdf_page()
        
        # 自动适应页面大小
        self.root.update()  # 确保界面已更新
        self.fit_to_page()
    
    def select_signature(self):
        file_path = filedialog.askopenfilename(
            title="选择签名图片",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp *.gif")]
        )
        if file_path:
            self.signature_path = file_path
            self.signature_label.config(text=os.path.basename(file_path))
            
            # 加载签名图片
            try:
                self.signature_image = Image.open(self.signature_path).convert("RGBA")
                self.add_sign_button.config(state=tk.NORMAL if self.pdf_path else tk.DISABLED)
                self.update_signature()
                self.save_button.config(state=tk.NORMAL if self.pdf_path and len(self.signatures) > 0 else tk.DISABLED)
                
                # 保存签名路径
                self.save_signature_path(self.signature_path)
            except Exception as e:
                messagebox.showerror("错误", f"无法打开签名图片: {str(e)}")
    
    def display_pdf_page(self):
        if not self.pdf_path:
            return
        
        # 显示加载中提示
        self.root.configure(cursor="wait")
        self.canvas.delete("all")
        loading_text = self.canvas.create_text(
            self.canvas.winfo_width() // 2,
            self.canvas.winfo_height() // 2,
            text="正在加载页面，请稍候...",
            font=(self.font_family, 16),
            fill="black"
        )
        self.root.update()
        
        # 检查缓存中是否已有当前页面的图像
        if self.current_page in self.page_cache:
            self.pdf_image = self.page_cache[self.current_page]
        else:
            try:
                # 获取当前页面
                page = self.pdf_reader.pages[self.current_page]
                
                # 避免使用convert_from_bytes直接处理，而是先保存为临时文件
                # 创建一个临时PDF用于显示
                output = PdfWriter()
                output.add_page(page)
                
                # 创建临时文件
                fd, temp_pdf_path = tempfile.mkstemp(suffix='.pdf')
                os.close(fd)
                self.temp_files.append(temp_pdf_path)
                
                # 将页面保存为临时文件
                with open(temp_pdf_path, 'wb') as f:
                    output.write(f)
                
                # 使用改进的转换方法
                self.pdf_image = self.convert_pdf_to_image(temp_pdf_path)
                
                # 缓存页面图像
                self.page_cache[self.current_page] = self.pdf_image
                
            except Exception as e:
                messagebox.showerror("错误", f"无法显示PDF页面: {str(e)}")
                self.root.configure(cursor="")
                return
        
        # 删除加载提示
        self.canvas.delete(loading_text)
        
        # 应用缩放
        width = int(self.pdf_image.width * self.zoom_factor)
        height = int(self.pdf_image.height * self.zoom_factor)
        
        # 调整后的图像
        if self.zoom_factor == 1.0:
            resized_image = self.pdf_image
        else:
            resized_image = self.pdf_image.resize((width, height), Image.LANCZOS)
        
        self.pdf_tk_image = ImageTk.PhotoImage(resized_image)
        
        # 计算画布可见区域的大小
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        # 设置完整滚动区域，确保足够大以填充整个视图或容纳PDF，以较大者为准
        padding_x = max(20, (canvas_width - width) // 2)
        padding_y = max(20, (canvas_height - height) // 2)
        
        # 确保滚动区域始终至少与画布一样大
        scroll_width = max(canvas_width, width + padding_x * 2)
        scroll_height = max(canvas_height, height + padding_y * 2)
        
        # 设置滚动区域
        self.canvas.config(scrollregion=(0, 0, scroll_width, scroll_height))
        
        # 清除画布
        self.canvas.delete("all")
        
        # 绘制全屏灰色背景，确保覆盖整个滚动区域
        self.canvas.create_rectangle(0, 0, scroll_width, scroll_height, 
                                    fill=self.canvas_bg, outline=self.canvas_bg, tags="bg")
        
        # 居中显示PDF
        pdf_x = padding_x
        pdf_y = padding_y
        self.canvas.create_image(pdf_x, pdf_y, anchor=tk.NW, image=self.pdf_tk_image, tags="pdf")
        
        # 确保pdf_document变量已初始化
        if not hasattr(self, 'pdf_document') or self.pdf_document is None:
            self.pdf_document = self.pdf_reader
        
        # 检查当前页是否有签名，如果有则显示
        if self.current_page in self.signatures:
            signature_data = self.signatures[self.current_page]
            
            # 处理不同格式的签名数据（兼容新旧格式）
            if isinstance(signature_data, tuple):
                if len(signature_data) == 2:  # 旧格式：(位置, 大小)
                    self.signature_position, self.signature_width = signature_data
                    self.signature_angle = 0  # 默认角度
                elif len(signature_data) >= 3:  # 新格式：(位置, 大小, 角度)
                    self.signature_position, self.signature_width, self.signature_angle = signature_data
            
            # 更新UI控件
            self.size_scale.set(self.signature_width)
            if hasattr(self, 'angle_scale'):
                self.angle_scale.set(self.signature_angle)
                
            # 显示签名
            if self.signature_image:
                self.update_signature(padding_x, padding_y)
            self.remove_sign_button.config(state=tk.NORMAL)
        else:
            # 如果当前页没有签名，设置默认位置在右下角
            # 计算右下角位置（考虑签名宽度和边距）
            default_x = self.pdf_image.width - self.signature_width - 50  # 距离右边缘50像素
            default_y = self.pdf_image.height - int(self.signature_width * 0.5) - 50  # 距离底部50像素
            self.signature_position = (default_x, default_y)
            self.canvas.delete("signature")
            self.remove_sign_button.config(state=tk.DISABLED)
            
        # 设置初始鼠标光标为箭头
        if self.cursor_over_pdf and not self.cursor_hand_active:
            self.canvas.config(cursor="arrow")
        
        # 恢复正常光标
        self.root.configure(cursor="")

    def convert_pdf_to_image(self, pdf_path):
        """将PDF页面转换为PIL图像"""
        try:
            # 尝试使用PyMuPDF (更快速且更可靠)
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(pdf_path)
                page = doc.load_page(0)  # 第一页
                
                # 获取合适的分辨率
                zoom = 2.0  # 较高分辨率，可根据需要调整
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                
                # 转换为PIL图像
                from PIL import Image
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                doc.close()
                return img
            except ImportError:
                print("未找到PyMuPDF，尝试使用pdf2image...")
                
            # 如果PyMuPDF不可用，尝试pdf2image
            from pdf2image import convert_from_path
            images = convert_from_path(
                pdf_path, 
                dpi=150,
                first_page=1,
                last_page=1,
                use_pdftocairo=True,
                thread_count=2  # 使用多线程加速
            )
            return images[0]
        except Exception as e:
            print(f"PDF转换为图像失败: {str(e)}")
            # 创建一个错误提示图像
            return self.create_error_image()

    def create_error_image(self):
        """创建一个错误提示图像"""
        img = Image.new('RGB', (800, 1000), color='white')
        return img

    def update_signature(self, padding_x=0, padding_y=0):
        if not self.signature_image:
            return
        
        # 确保PDF已加载
        if not hasattr(self, 'pdf_image') or self.pdf_image is None:
            return
        
        # 删除旧的签名图像
        self.canvas.delete("signature")
        
        # 调整签名大小
        width = int(self.signature_width * self.zoom_factor)
        ratio = width / (self.signature_image.width * self.zoom_factor)
        height = int(self.signature_image.height * self.zoom_factor * ratio)
        
        # 调整签名位置以适应缩放和居中 - 使用与旧版本一致的计算方式
        scaled_x = self.signature_position[0] * self.zoom_factor + padding_x
        scaled_y = self.signature_position[1] * self.zoom_factor + padding_y
        
        # 复制签名图像，保持原始透明度
        signature_copy = self.signature_image.copy()
        
        # 使用高质量的重采样方法
        resized_signature = signature_copy.resize((width, height), Image.LANCZOS)
        
        # 应用旋转
        if hasattr(self, 'signature_angle') and self.signature_angle != 0:
            # 使用PIL旋转图片，保留透明度
            resized_signature = resized_signature.rotate(self.signature_angle, resample=Image.BICUBIC, expand=True)
        
        self.signature_tk_image = ImageTk.PhotoImage(resized_signature)
        
        # 显示签名
        self.signature_id = self.canvas.create_image(
            scaled_x, 
            scaled_y, 
            anchor=tk.NW, 
            image=self.signature_tk_image,
            tags="signature"
        )
    
    def update_signature_size(self, value):
        self.signature_width = int(float(value))
        # 更新尺寸显示标签
        if hasattr(self, 'size_value_label'):
            self.size_value_label.config(text=f"{self.signature_width}px")
        if self.signature_image:
            # 计算画布可见区域的大小
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            # 设置完整滚动区域，确保足够大以填充整个视图或容纳PDF，以较大者为准
            width = int(self.pdf_image.width * self.zoom_factor) if self.pdf_image else 0
            height = int(self.pdf_image.height * self.zoom_factor) if self.pdf_image else 0
            padding_x = max(20, (canvas_width - width) // 2)
            padding_y = max(20, (canvas_height - height) // 2)
            
            # 更新签名显示
            self.update_signature(padding_x, padding_y)
            
            # 如果当前页已添加签名，更新签名信息
            if self.current_page in self.signatures:
                signature_data = self.signatures[self.current_page]
                if isinstance(signature_data, tuple):
                    if len(signature_data) >= 3:
                        self.signatures[self.current_page] = (self.signature_position, self.signature_width, self.signature_angle)
                    else:
                        # 确保signature_angle已定义
                        if not hasattr(self, 'signature_angle'):
                            self.signature_angle = 0
                        # 更新为新格式
                        self.signatures[self.current_page] = (self.signature_position, self.signature_width, self.signature_angle)
    
    def update_signature_angle(self, value):
        self.signature_angle = int(float(value))
        # 更新角度显示标签
        if hasattr(self, 'angle_value_label'):
            self.angle_value_label.config(text=f"{self.signature_angle}°")
        if self.signature_image:
            # 计算画布可见区域的大小
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            # 设置完整滚动区域，确保足够大以填充整个视图或容纳PDF，以较大者为准
            width = int(self.pdf_image.width * self.zoom_factor) if self.pdf_image else 0
            height = int(self.pdf_image.height * self.zoom_factor) if self.pdf_image else 0
            padding_x = max(20, (canvas_width - width) // 2)
            padding_y = max(20, (canvas_height - height) // 2)
            
            # 更新签名显示
            self.update_signature(padding_x, padding_y)
            
            # 如果当前页已添加签名，更新签名信息
            if self.current_page in self.signatures:
                signature_data = self.signatures[self.current_page]
                if isinstance(signature_data, tuple):
                    if len(signature_data) >= 3:
                        self.signatures[self.current_page] = (self.signature_position, self.signature_width, self.signature_angle)
                    else:
                        # 更新为新格式
                        self.signatures[self.current_page] = (self.signature_position, self.signature_width, self.signature_angle)
    
    def set_signature_angle(self, angle):
        self.signature_angle = angle
        # 更新角度滑块
        if hasattr(self, 'angle_scale'):
            self.angle_scale.set(angle)
        # 更新角度显示标签
        if hasattr(self, 'angle_value_label'):
            self.angle_value_label.config(text=f"{self.signature_angle}°")
        if self.signature_image:
            # 计算画布可见区域的大小
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            # 设置完整滚动区域，确保足够大以填充整个视图或容纳PDF，以较大者为准
            width = int(self.pdf_image.width * self.zoom_factor) if self.pdf_image else 0
            height = int(self.pdf_image.height * self.zoom_factor) if self.pdf_image else 0
            padding_x = max(20, (canvas_width - width) // 2)
            padding_y = max(20, (canvas_height - height) // 2)
            
            # 更新签名显示
            self.update_signature(padding_x, padding_y)
            
            # 如果当前页已添加签名，更新签名信息
            if self.current_page in self.signatures:
                signature_data = self.signatures[self.current_page]
                if isinstance(signature_data, tuple):
                    if len(signature_data) >= 3:
                        self.signatures[self.current_page] = (self.signature_position, self.signature_width, self.signature_angle)
                    else:
                        # 更新为新格式
                        self.signatures[self.current_page] = (self.signature_position, self.signature_width, self.signature_angle)
                        
    def add_signature_to_page(self):
        """将签名添加到当前页面"""
        if not self.signature_image:
            self.show_error("请先选择一个签名图片")
            return
        
        # 确保pdf_document变量已正确初始化
        if not hasattr(self, 'pdf_document') or self.pdf_document is None:
            if hasattr(self, 'pdf_reader') and self.pdf_reader is not None:
                self.pdf_document = self.pdf_reader
            else:
                self.show_error("请先选择一个PDF文件")
                return
        
        # 更新签名位置到当前页面
        if not hasattr(self, 'signature_angle'):
            self.signature_angle = 0  # 设置默认角度
            
        self.signatures[self.current_page] = (
            self.signature_position, 
            self.signature_width,
            self.signature_angle
        )
        
        # 立即更新画布上的签名显示
        if self.signature_image:
            # 计算画布可见区域的大小
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            # 设置完整滚动区域，确保足够大以填充整个视图或容纳PDF，以较大者为准
            width = int(self.pdf_image.width * self.zoom_factor) if self.pdf_image else 0
            height = int(self.pdf_image.height * self.zoom_factor) if self.pdf_image else 0
            padding_x = max(20, (canvas_width - width) // 2)
            padding_y = max(20, (canvas_height - height) // 2)
            
            # 更新签名显示
            self.update_signature(padding_x, padding_y)
        
        # 更新签名页面列表
        self.update_signed_pages_list()
        
        # 更新UI按钮状态
        self.remove_sign_button.config(state=tk.NORMAL)
        self.save_button.config(state=tk.NORMAL)  # 激活保存按钮
        
        # 显示成功消息
        messagebox.showinfo("成功", f"已将签名添加到第 {self.current_page + 1} 页")
    
    def remove_signature_from_page(self):
        """从当前页面移除签名"""
        if self.current_page in self.signatures:
            # 从签名字典中移除当前页
            del self.signatures[self.current_page]
            
            # 删除画布上的签名图像
            self.canvas.delete("signature")
            
            # 更新签名页面列表
            self.update_signed_pages_list()
            
            # 如果没有签名页面了，禁用移除按钮
            if not self.signatures:
                self.remove_sign_button.config(state=tk.DISABLED)
    
    def update_signed_pages_list(self):
        """更新已签名页面列表"""
        self.signed_pages_listbox.delete(0, tk.END)
        self.signed_pages_list = sorted(self.signatures.keys())
        
        for page in self.signed_pages_list:
            self.signed_pages_listbox.insert(tk.END, f"第 {page + 1} 页")
    
    def on_signed_page_selected(self, event):
        """当用户选择已签名页面时，跳转到对应页面"""
        selected_indices = self.signed_pages_listbox.curselection()
        if not selected_indices:
            return
            
        # 获取所选页面的索引和页码
        selected_index = selected_indices[0]
        page_number = self.signed_pages_list[selected_index]
        
        # 载入对应页面
        if self.current_page != page_number:
            self.current_page = page_number
            self.display_pdf_page()
            
            # 更新页面信息
            self.page_label.config(text=f"{self.current_page + 1} / {len(self.pdf_document.pages)}")
            self.page_entry.current(self.current_page)
            
            # 恢复签名位置、大小和角度
            if page_number in self.signatures:
                signature_data = self.signatures[page_number]
                # 处理不同格式的签名数据
                if isinstance(signature_data, tuple):
                    if len(signature_data) == 2:  # 旧格式：(位置, 大小)
                        self.signature_position, self.signature_width = signature_data
                        self.signature_angle = 0  # 默认角度
                    elif len(signature_data) >= 3:  # 新格式：(位置, 大小, 角度)
                        self.signature_position, self.signature_width, self.signature_angle = signature_data
                
                # 更新UI控件
                self.size_scale.set(self.signature_width)
                if hasattr(self, 'angle_scale'):
                    self.angle_scale.set(self.signature_angle)
    
    def save_pdf(self):
        if not self.pdf_path or not self.signature_path or not self.signatures:
            messagebox.showerror("错误", "请先选择PDF、签名图片，并至少为一页添加签名")
            return
        
        # 获取原文件名（不含扩展名）并添加"_已签名"后缀
        original_filename = os.path.splitext(os.path.basename(self.pdf_path))[0]
        default_filename = f"{original_filename}_已签名.pdf"
        
        save_path = filedialog.asksaveasfilename(
            title="保存签名后的PDF",
            defaultextension=".pdf",
            initialfile=default_filename,
            filetypes=[("PDF文件", "*.pdf")]
        )
        
        if not save_path:
            return
        
        try:
            # 显示进度提示
            progress_window = tk.Toplevel(self.root)
            progress_window.title("处理中")
            progress_window.geometry("300x100")
            progress_window.transient(self.root)
            progress_window.grab_set()
            progress_window.resizable(False, False)
            
            # 设置窗口图标与主窗口相同
            try:
                # 直接使用之前保存的图标对象，或者创建一个空图标
                if hasattr(self.root, '_icon_photo'):
                    progress_window.iconphoto(False, self.root._icon_photo)
            except Exception:
                # 如果设置图标失败，静默忽略，不影响主要功能
                pass
            
            # 创建进度条
            progress_label = ttk.Label(progress_window, text="正在处理PDF，请稍候...", font=self.normal_font)
            progress_label.pack(pady=(15, 5))
            
            progress_bar = ttk.Progressbar(progress_window, mode='indeterminate')
            progress_bar.pack(fill=tk.X, padx=20, pady=5)
            progress_bar.start(10)
            
            # 更新UI
            self.root.update()
            
            # 使用后台线程处理PDF
            import threading
            
            def process_pdf_task():
                try:
                    # 读取原始PDF
                    input_pdf = PdfReader(self.pdf_path)
                    output_pdf = PdfWriter()
                    
                    # 生成防伪标记数据
                    if self.watermark_enabled:
                        self.watermark_data = self.generate_watermark_data()
                    
                    # 处理每一页
                    for i in range(len(input_pdf.pages)):
                        # 更新进度标签
                        progress_window.after(0, lambda idx=i, total=len(input_pdf.pages): 
                                          progress_label.config(text=f"正在处理第 {idx+1}/{total} 页..."))
                        
                        page = input_pdf.pages[i]
                        
                        # 检查该页是否需要添加签名
                        if i in self.signatures:
                            # 获取签名数据，确保兼容不同格式
                            signature_data = self.signatures[i]
                            
                            # 处理不同格式的签名数据
                            if isinstance(signature_data, tuple):
                                if len(signature_data) >= 3:  # 新格式：(位置, 大小, 角度)
                                    signature_position, signature_width, signature_angle = signature_data
                                else:  # 旧格式：(位置, 大小)
                                    signature_position, signature_width = signature_data
                                    signature_angle = 0  # 默认角度
                            else:
                                # 意外情况，跳过处理这一页的签名
                                output_pdf.add_page(page)
                                continue
                            
                            # 准备签名图片
                            width = signature_width
                            ratio = width / self.signature_image.width
                            height = int(self.signature_image.height * ratio)
                            
                            # 复制签名图像，保持原始质量
                            signature_copy = self.signature_image.copy()
                            
                            # 高质量调整大小
                            resized_signature = signature_copy.resize((width, height), Image.LANCZOS)
                            
                            # 应用旋转
                            if signature_angle != 0:
                                # 使用PIL旋转图片，保留透明度
                                resized_signature = resized_signature.rotate(signature_angle, resample=Image.BICUBIC, expand=True)
                            
                            # 获取页面尺寸
                            page_width = float(page.mediabox.width)
                            page_height = float(page.mediabox.height)
                            
                            # 创建临时文件以获得正确的缩放比例
                            fd, temp_pdf_path = tempfile.mkstemp(suffix='.pdf')
                            os.close(fd)
                            self.temp_files.append(temp_pdf_path)
                            
                            temp_output = PdfWriter()
                            temp_output.add_page(page)
                            
                            with open(temp_pdf_path, 'wb') as f:
                                temp_output.write(f)
                            
                            # 获取页面图像尺寸
                            temp_image = self.convert_pdf_to_image(temp_pdf_path)
                            
                            # 计算签名在PDF中的正确位置和尺寸
                            # 获取页面图像尺寸
                            temp_image = self.convert_pdf_to_image(temp_pdf_path)
                            
                            # 计算比例
                            scale_x = page_width / temp_image.width
                            scale_y = page_height / temp_image.height
                            
                            # 计算签名的实际大小
                            signature_width_in_pdf = resized_signature.width * scale_x
                            signature_height_in_pdf = resized_signature.height * scale_y
                            
                            # 计算签名位置（使用类似旧版的坐标计算方式）
                            signature_x = signature_position[0] * scale_x
                            # PDF坐标系从底部开始，而图像从顶部开始，所以需要翻转y坐标
                            signature_y = page_height - (signature_position[1] + resized_signature.height) * scale_y
                            
                            # 创建包含签名的临时PDF
                            packet = io.BytesIO()
                            # 使用页面实际尺寸创建Canvas
                            can = canvas.Canvas(packet, pagesize=(page_width, page_height))
                            
                            # 将签名图片保存为临时文件（使用高质量设置）
                            fd, temp_sig_path = tempfile.mkstemp(suffix='.png')
                            os.close(fd)
                            self.temp_files.append(temp_sig_path)
                            resized_signature.save(temp_sig_path, "PNG", dpi=(300, 300), quality=95)
                            
                            # 添加签名图片
                            can.saveState()
                            # 使用与历史版本相同的方式绘制签名
                            can.drawImage(temp_sig_path, signature_x, signature_y, 
                                         width=signature_width_in_pdf, 
                                         height=signature_height_in_pdf, 
                                         mask='auto')
                            
                            # 添加防伪水印
                            if self.watermark_enabled:
                                can.setFont("Helvetica", 0.5)  # 极小字体
                                can.setFillColorRGB(0.97, 0.97, 0.97)  # 接近白色
                                
                                # 在签名右下角添加水印标记信息
                                mark_text = f"SIG:{self.watermark_data['signature_id'][:8]}|{i}"
                                can.drawString(signature_x + signature_width_in_pdf*0.9, 
                                             signature_y, mark_text)
                            
                            can.restoreState()
                            can.save()
                            
                            # 将签名叠加到原始页面上
                            packet.seek(0)
                            signature_pdf = PdfReader(packet)
                            signature_page = signature_pdf.pages[0]
                            
                            page.merge_page(signature_page)
                        
                        output_pdf.add_page(page)
                    
                    # 添加防伪元数据
                    if self.watermark_enabled:
                        self.embed_watermark_to_pdf(output_pdf, self.watermark_data)
                    
                    # 保存最终PDF，使用更高的压缩质量
                    with open(save_path, "wb") as output_file:
                        output_pdf.write(output_file)
                    
                    # 操作完成，在主线程中关闭进度窗口并显示成功信息
                    progress_window.after(0, lambda: self.finish_save(progress_window, "PDF已成功保存签名和防伪标记！"))
                    
                except Exception as e:
                    # 发生错误，在主线程中关闭进度窗口并显示错误信息
                    progress_window.after(0, lambda err=str(e): self.finish_save(progress_window, f"保存PDF时出错: {err}", is_error=True))
            
            # 启动后台线程，不显示命令行窗口
            thread = threading.Thread(target=process_pdf_task, daemon=True)
            thread.name = "PDF保存线程"  # 设置线程名称，便于调试
            thread.start()
            
        except Exception as e:
            if 'progress_window' in locals() and progress_window.winfo_exists():
                progress_window.destroy()
            messagebox.showerror("错误", f"保存PDF时出错: {str(e)}")
    
    def finish_save(self, progress_window, message, is_error=False):
        """完成保存操作，关闭进度窗口并显示消息"""
        progress_window.destroy()
        if is_error:
            messagebox.showerror("错误", message)
        else:
            messagebox.showinfo("成功", message)

    def on_mouse_enter(self, event):
        """鼠标进入画布区域时触发"""
        self.cursor_over_pdf = True
        # 默认显示箭头光标
        self.canvas.config(cursor="arrow")
    
    def on_mouse_leave(self, event):
        """鼠标离开画布区域时触发"""
        self.cursor_over_pdf = False
        # 恢复默认光标
        self.canvas.config(cursor="")
        self.cursor_hand_active = False

    def on_window_resize(self, event):
        """处理窗口大小改变事件，动态调整PDF显示区域"""
        # 只处理来自root窗口的事件，避免子组件的Configure事件
        if event.widget == self.root:
            # 获取当前窗口尺寸
            current_width = self.root.winfo_width()
            current_height = self.root.winfo_height()
            
            # 判断窗口大小是否有显著变化(超过10像素)
            width_changed = abs(current_width - self.last_window_width) > 10
            height_changed = abs(current_height - self.last_window_height) > 10
            
            if width_changed or height_changed:
                # 更新记录的窗口大小
                self.last_window_width = current_width
                self.last_window_height = current_height
                
                # 延迟执行大小适应，避免频繁刷新
                if hasattr(self, 'resize_timer') and self.resize_timer:
                    self.root.after_cancel(self.resize_timer)
                self.resize_timer = self.root.after(100, self.auto_fit_to_window)
    
    def auto_fit_to_window(self):
        """窗口大小改变时自动调整PDF缩放比例以适合窗口大小"""
        if not self.pdf_image:
            return
        
        # 获取当前预览区域的可用空间
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        # 确保尺寸合理
        if canvas_width < 100 or canvas_height < 100:
            # 延迟执行，等待布局完成
            self.root.after(100, self.auto_fit_to_window)
            return
        
        # 计算保持宽高比的缩放因子
        width_ratio = (canvas_width - 40) / self.pdf_image.width  # 留出20像素边距
        height_ratio = (canvas_height - 40) / self.pdf_image.height  # 留出20像素边距
        
        # 选择较小的比例确保整个PDF可见
        new_zoom = min(width_ratio, height_ratio) * 0.95  # 增加5%的额外边距
        
        # 如果缩放变化超过10%，则更新缩放比例
        if abs(new_zoom - self.zoom_factor) / self.zoom_factor > 0.1:
            self.zoom_factor = new_zoom
            self.update_zoom()
        else:
            # 即使缩放比例没有显著变化，也需要更新视图以适应新窗口大小
            self.resize_pdf_view()
    
    def resize_pdf_view(self):
        """根据当前窗口大小调整PDF显示"""
        if not self.pdf_image:
            return
            
        # 重新计算画布可见区域的大小
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        if canvas_width < 100 or canvas_height < 100:
            # 画布尚未完全初始化，忽略
            return
            
        # 应用缩放
        width = int(self.pdf_image.width * self.zoom_factor)
        height = int(self.pdf_image.height * self.zoom_factor)
        
        # 计算padding，确保居中显示，并且至少有20像素的边距
        padding_x = max(20, (canvas_width - width) // 2)
        padding_y = max(20, (canvas_height - height) // 2)
        
        # 确保滚动区域始终至少与画布一样大
        scroll_width = max(canvas_width, width + padding_x * 2)
        scroll_height = max(canvas_height, height + padding_y * 2)
        
        # 设置滚动区域
        self.canvas.config(scrollregion=(0, 0, scroll_width, scroll_height))
        
        # 重绘PDF和签名
        self.canvas.delete("all")
        
        # 绘制全屏灰色背景，确保覆盖整个滚动区域
        self.canvas.create_rectangle(0, 0, scroll_width, scroll_height, 
                                    fill=self.canvas_bg, outline=self.canvas_bg, tags="bg")
        
        # 绘制PDF
        self.canvas.create_image(padding_x, padding_y, anchor=tk.NW, image=self.pdf_tk_image, tags="pdf")
        
        # 如果当前页有签名，重新显示签名
        if self.current_page in self.signatures and self.signature_image:
            self.update_signature(padding_x, padding_y)

    def save_signature_path(self, signature_path):
        try:
            with open('signature_config.json', 'w') as f:
                json.dump({'last_signature': signature_path}, f)
        except Exception as e:
            print(f"保存签名配置失败: {str(e)}")

    def load_last_signature_path(self):
        try:
            if os.path.exists('signature_config.json'):
                with open('signature_config.json', 'r') as f:
                    config = json.load(f)
                    self.signature_path = config.get('last_signature')
                    if self.signature_path and os.path.exists(self.signature_path):
                        self.signature_label.config(text=os.path.basename(self.signature_path))
                        try:
                            self.signature_image = Image.open(self.signature_path).convert("RGBA")
                            self.add_sign_button.config(state=tk.NORMAL if self.pdf_path else tk.DISABLED)
                            self.update_signature()
                            self.save_button.config(state=tk.NORMAL if self.pdf_path and len(self.signatures) > 0 else tk.DISABLED)
                        except Exception as e:
                            print(f"无法打开签名图片: {str(e)}")
                            self.signature_path = None
        except Exception as e:
            print(f"加载签名配置失败: {str(e)}")
            
    def on_closing(self):
        """窗口关闭时清理临时文件"""
        try:
            for temp_file in self.temp_files:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
        except Exception as e:
            print(f"清理临时文件时出错: {str(e)}")
        self.root.destroy()

    def get_computer_info(self):
        """获取当前计算机的基本信息"""
        try:
            computer_info = {
                "系统": platform.system(),
                "版本": platform.version(),
                "计算机名": platform.node(),
                "处理器": platform.processor(),
                "系统架构": platform.architecture()[0],
                "IP地址": self.get_ip_address(),
                "系统时区": datetime.datetime.now().astimezone().tzname()
            }
            return computer_info
        except Exception as e:
            print(f"获取计算机信息时出错: {str(e)}")
            return {"系统": "未知", "错误": str(e)}
    
    def get_ip_address(self):
        """获取当前计算机的IP地址"""
        try:
            # 创建临时socket连接以获取本地IP地址
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip_address = s.getsockname()[0]
            s.close()
            return ip_address
        except:
            # 如果无法连接外网，尝试获取主机名对应的IP
            try:
                return socket.gethostbyname(socket.gethostname())
            except:
                return "未知"
    
    def generate_watermark_data(self):
        """生成防伪标记数据"""
        # 创建唯一的签名ID和时间戳
        signature_id = str(uuid.uuid4())
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 计算PDF文件的哈希值
        pdf_hash = self.calculate_file_hash(self.pdf_path)
        
        # 计算签名图像的哈希值
        signature_hash = self.calculate_file_hash(self.signature_path)
        
        # 将所有签名页的信息合并
        pages_info = {}
        for page_num, signature_data in self.signatures.items():
            # 处理不同格式的签名数据
            if isinstance(signature_data, tuple):
                if len(signature_data) == 2:  # 旧格式：(位置, 大小)
                    pos, width = signature_data
                    angle = 0  # 默认角度
                elif len(signature_data) >= 3:  # 新格式：(位置, 大小, 角度)
                    pos, width, angle = signature_data
                else:
                    # 意外情况，跳过处理
                    continue
            else:
                # 格式不是元组，跳过处理
                continue
                
            pages_info[str(page_num)] = {
                "position": [float(pos[0]), float(pos[1])],
                "width": float(width),
                "angle": float(angle)  # 添加角度信息
            }
        
        # 获取计算机信息
        computer_info = self.get_computer_info()
        
        # 构建完整的防伪数据
        watermark_data = {
            "signature_id": signature_id,
            "timestamp": timestamp,
            "pdf_hash": pdf_hash,
            "signature_hash": signature_hash,
            "pages_info": pages_info,
            "computer_info": computer_info,
            "software": "PDF签名工具 v1.0"
        }
        
        return watermark_data
    
    def calculate_file_hash(self, file_path):
        """计算文件的SHA-256哈希值"""
        try:
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                # 读取文件块并更新哈希
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            print(f"计算文件哈希值时出错: {str(e)}")
            return "unknown_hash"
    
    def embed_watermark_to_pdf(self, output_pdf, watermark_data):
        """将防伪标记嵌入到PDF文件的元数据中"""
        try:
            # 将防伪数据转换为JSON字符串，并进行Base64编码
            watermark_json = json.dumps(watermark_data, ensure_ascii=False)
            encoded_watermark = base64.b64encode(watermark_json.encode('utf-8')).decode('ascii')
            
            # 添加自定义元数据
            output_pdf.add_metadata({
                "/PDFSignatureWatermark": encoded_watermark
            })
            
            return True
        except Exception as e:
            print(f"嵌入防伪标记时出错: {str(e)}")
            return False
    
    def extract_watermark_from_pdf(self, pdf_path):
        """从PDF文件中提取防伪标记"""
        try:
            reader = PdfReader(pdf_path)
            if "/PDFSignatureWatermark" in reader.metadata:
                encoded_watermark = reader.metadata["/PDFSignatureWatermark"]
                # 解码Base64字符串并转换为JSON对象
                watermark_json = base64.b64decode(encoded_watermark).decode('utf-8')
                watermark_data = json.loads(watermark_json)
                return watermark_data
            else:
                return None
        except Exception as e:
            print(f"提取防伪标记时出错: {str(e)}")
            return None
    
    def verify_pdf_watermark(self, pdf_path):
        """验证PDF文件的防伪标记"""
        watermark_data = self.extract_watermark_from_pdf(pdf_path)
        if not watermark_data:
            return False, "未找到防伪标记"
        
        # 验证PDF哈希值
        current_pdf_hash = self.calculate_file_hash(pdf_path)
        original_pdf_hash = watermark_data.get("pdf_hash")
        
        # 注意：PDF被修改后哈希值将不同，所以不应该直接比较pdf_hash
        # 这里只验证防伪标记的存在性和完整性
        
        # 获取当前计算机信息，用于比较
        current_computer_info = self.get_computer_info()
        original_computer_info = watermark_data.get("computer_info", {})
        
        # 判断是否是本机签名
        is_same_computer = False
        if original_computer_info:
            # 检查计算机信息是否完全一致
            is_same_computer = True
            
            # 必须匹配的关键信息项（确保计算机一致性验证）
            crucial_info_keys = ["计算机名", "系统", "系统架构", "处理器"]
            
            # 检查每个关键信息是否一致
            for key in crucial_info_keys:
                if current_computer_info.get(key) != original_computer_info.get(key):
                    is_same_computer = False
                    break
        
        # 构建验证结果
        result = {
            "签名ID": watermark_data.get("signature_id", "未知"),
            "签名时间": watermark_data.get("timestamp", "未知"),
            "签名软件": watermark_data.get("software", "未知"),
            "签名页面": len(watermark_data.get("pages_info", {})),
            "计算机信息": watermark_data.get("computer_info", {}),
            "是否本机签名": is_same_computer
        }
        
        # 只有当计算机信息完全一致时，才返回验证成功
        if is_same_computer:
            return True, result
        else:
            return False, "计算机信息不匹配，验证失败"
    
    def hide_console_again(self):
        """此方法不再需要，保留空实现以兼容代码"""
        pass

    def start_drag(self, event):
        """开始拖动处理"""
        # 获取PDF的偏移量（用于居中显示时计算正确的拖拽位置）
        canvas_width = self.canvas.winfo_width()
        width = int(self.pdf_image.width * self.zoom_factor) if self.pdf_image else 0
        padding_x = max(0, (canvas_width - width) // 2)
        
        canvas_height = self.canvas.winfo_height()
        height = int(self.pdf_image.height * self.zoom_factor) if self.pdf_image else 0
        padding_y = max(0, (canvas_height - height) // 2)
            
        # 检查是否点击在签名上
        items = self.canvas.find_withtag(tk.CURRENT)
        if items and "signature" in self.canvas.gettags(items[0]):
            # 签名拖动模式
            self.signature_dragging = True
            self.page_dragging = False
            self.drag_start_x = event.x
            self.drag_start_y = event.y
            
            # 记录签名原始位置 - 使用与旧版本一致的计算方式
            self.drag_start_pos = (
                (self.signature_position[0] * self.zoom_factor) + padding_x,
                (self.signature_position[1] * self.zoom_factor) + padding_y
            )
            self.padding_x = padding_x
            self.padding_y = padding_y
            # 签名拖动时使用移动光标
            self.canvas.config(cursor="fleur")
            self.cursor_hand_active = True
        else:
            # PDF页面拖动模式
            self.signature_dragging = False
            self.page_dragging = True
            self.drag_start_x = event.x
            self.drag_start_y = event.y
            # 记录当前画布滚动位置
            self.scroll_start_x = self.canvas.canvasx(0)
            self.scroll_start_y = self.canvas.canvasy(0)
            # PDF拖动时使用抓手光标（Adobe风格）
            self.canvas.config(cursor="hand2")
            self.cursor_hand_active = True

    def drag(self, event):
        """拖动处理"""
        if self.signature_dragging:
            # 签名拖动逻辑
            dx = event.x - self.drag_start_x
            dy = event.y - self.drag_start_y
            new_x = self.drag_start_pos[0] + dx
            new_y = self.drag_start_pos[1] + dy
            
            # 更新签名位置 - 使用与旧版本一致的计算方式
            self.signature_position = (
                (new_x - self.padding_x) / self.zoom_factor, 
                (new_y - self.padding_y) / self.zoom_factor
            )
            
            # 确保签名不会被拖动到PDF页面外
            if self.pdf_image:
                pdf_width = self.pdf_image.width
                pdf_height = self.pdf_image.height
                
                # 获取签名尺寸
                signature_width = self.signature_width
                signature_height = int(self.signature_width * (self.signature_image.height / self.signature_image.width))
                
                # 限制X坐标
                self.signature_position = (
                    max(0, min(self.signature_position[0], pdf_width - signature_width)),
                    self.signature_position[1]
                )
                
                # 限制Y坐标
                self.signature_position = (
                    self.signature_position[0],
                    max(0, min(self.signature_position[1], pdf_height - signature_height))
                )
            
            # 更新画布上的位置 - 直接使用计算得到的坐标
            self.canvas.coords(self.signature_id, new_x, new_y)
            
            # 如果当前页已添加签名，更新签名信息
            if self.current_page in self.signatures:
                signature_data = self.signatures[self.current_page]
                if isinstance(signature_data, tuple):
                    if len(signature_data) >= 3:
                        self.signatures[self.current_page] = (self.signature_position, self.signature_width, self.signature_angle)
                    else:
                        # 确保signature_angle存在
                        if not hasattr(self, 'signature_angle'):
                            self.signature_angle = 0
                        # 更新为新格式
                        self.signatures[self.current_page] = (self.signature_position, self.signature_width, self.signature_angle)
                
        elif self.page_dragging and self.pdf_image:  # 确保PDF已加载
            current_time = event.time if hasattr(event, 'time') else 0
            dx = event.x - self.drag_start_x
            dy = event.y - self.drag_start_y
            
            # 计算拖动距离
            drag_distance = (dx**2 + dy**2)**0.5
            
            # 只在移动超过最小距离时响应
            if drag_distance < self.min_drag_distance:
                return
            
            # 计算时间差（毫秒）
            time_diff = current_time - self.last_drag_time if self.last_drag_time > 0 else 1
            if time_diff > 0:
                # 计算当前速度（像素/毫秒）
                current_speed = drag_distance / time_diff
                self.drag_speed_history.append(current_speed)
                if len(self.drag_speed_history) > self.max_speed_history:
                    self.drag_speed_history.pop(0)
            
            # 计算平均速度
            avg_speed = sum(self.drag_speed_history) / len(self.drag_speed_history) if self.drag_speed_history else 0
            
            # 根据速度动态调整灵敏度
            speed_factor = min(1.5, max(0.5, 1.0 + avg_speed * 0.1))
            
            # 计算平滑的滚动单位
            dx_units = -int(dx * speed_factor)
            dy_units = -int(dy * speed_factor)
            
            # 应用滚动
            if dx_units != 0:
                self.canvas.xview_scroll(dx_units, "units")
            if dy_units != 0:
                self.canvas.yview_scroll(dy_units, "units")
            
            # 更新拖动起点和时间
            self.drag_start_x = event.x
            self.drag_start_y = event.y
            self.last_drag_time = current_time
            self.last_drag_pos = [event.x, event.y]
            
            # 更新速度向量（用于惯性滚动）
            speed_dampening = 0.85  # 速度平滑因子
            self.drag_velocity[0] = self.drag_velocity[0] * (1-speed_dampening) + dx * speed_dampening
            self.drag_velocity[1] = self.drag_velocity[1] * (1-speed_dampening) + dy * speed_dampening

    def stop_drag(self, event):
        """停止拖动处理"""
        if self.page_dragging and self.drag_inertia and self.pdf_image:
            # 启动惯性滚动
            self._start_inertia_scrolling()
        
        self.signature_dragging = False
        self.page_dragging = False
        
        # 拖动结束后，恢复为箭头光标（Adobe风格）
        if self.cursor_over_pdf:
            self.canvas.config(cursor="arrow")
        else:
            self.canvas.config(cursor="")
        self.cursor_hand_active = False
        
    def _start_inertia_scrolling(self):
        """启动Adobe风格的惯性滚动"""
        if abs(self.drag_velocity[0]) < 0.5 and abs(self.drag_velocity[1]) < 0.5:
            return  # 速度太小，不需要惯性滚动
            
        # 计算当前速度
        current_speed = (self.drag_velocity[0]**2 + self.drag_velocity[1]**2)**0.5
        
        # 根据速度动态调整减速因子
        speed_factor = min(1.0, max(0.5, current_speed * 0.1))
        current_deceleration = self.drag_deceleration * speed_factor
        
        # 计算滚动单位
        x_units = -int(self.drag_velocity[0])
        y_units = -int(self.drag_velocity[1])
        
        if x_units == 0 and y_units == 0:
            return
            
        # 应用滚动
        if x_units != 0:
            self.canvas.xview_scroll(x_units, "units")
        if y_units != 0:
            self.canvas.yview_scroll(y_units, "units")
            
        # 应用动态减速
        self.drag_velocity[0] *= current_deceleration
        self.drag_velocity[1] *= current_deceleration
        
        # 继续惯性滚动直到速度足够小
        if abs(self.drag_velocity[0]) > 0.5 or abs(self.drag_velocity[1]) > 0.5:
            inertia_interval = 16  # 约60fps的刷新率
            self.drag_momentum_timer = self.root.after(inertia_interval, self._start_inertia_scrolling)
        else:
            self.drag_velocity = [0, 0]  # 重置速度
            self.drag_speed_history = []  # 清空速度历史

    def previous_page(self):
        """导航到上一页"""
        if self.current_page > 0:
            self.current_page -= 1
            self.page_label.config(text=f"{self.current_page + 1} / {self.total_pages}")
            if hasattr(self, 'page_entry') and self.page_entry.winfo_exists():
                self.page_entry.current(self.current_page)
            self.display_pdf_page()
            
            # 更新按钮状态
            self.prev_button.config(state=tk.NORMAL if self.current_page > 0 else tk.DISABLED)
            self.next_button.config(state=tk.NORMAL)
    
    def next_page(self):
        """导航到下一页"""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.page_label.config(text=f"{self.current_page + 1} / {self.total_pages}")
            if hasattr(self, 'page_entry') and self.page_entry.winfo_exists():
                self.page_entry.current(self.current_page)
            self.display_pdf_page()
            
            # 更新按钮状态
            self.prev_button.config(state=tk.NORMAL)
            self.next_button.config(state=tk.NORMAL if self.current_page < self.total_pages - 1 else tk.DISABLED)
    
    def jump_to_page(self, event):
        """跳转到指定页面"""
        if hasattr(self, 'page_entry') and self.page_entry.winfo_exists() and self.page_entry.get():
            try:
                page_num = int(self.page_entry.get()) - 1  # 转换为0-based索引
                if 0 <= page_num < self.total_pages:
                    self.current_page = page_num
                    self.page_label.config(text=f"{self.current_page + 1} / {self.total_pages}")
                    self.display_pdf_page()
                    
                    # 更新按钮状态
                    self.prev_button.config(state=tk.NORMAL if self.current_page > 0 else tk.DISABLED)
                    self.next_button.config(state=tk.NORMAL if self.current_page < self.total_pages - 1 else tk.DISABLED)
            except ValueError:
                pass

# 主程序
if __name__ == "__main__":
    # 设置未处理异常的全局处理器
    def show_error_and_exit(exc_type, exc_value, exc_traceback):
        import traceback
        error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        
        # 仅在非打包模式下打印错误
        if not getattr(sys, 'frozen', False):
            print(f"未捕获的异常: {error_msg}")
            
        try:
            from tkinter import messagebox
            messagebox.showerror("错误", f"程序发生错误: {str(exc_value)}\n请重新启动程序")
        except:
            pass
        sys.exit(1)
        
    sys.excepthook = show_error_and_exit
    
    # 仅在非打包模式下检查必要的库是否已安装
    if not getattr(sys, 'frozen', False):
        required_libraries = ['PyPDF2', 'PIL.Image', 'reportlab.pdfgen.canvas']
        missing_libraries = []
        
        for lib in required_libraries:
            try:
                __import__(lib.split('.')[0])
            except ImportError:
                missing_libraries.append(lib)
        
        if missing_libraries:
            try:
                from tkinter import messagebox, Tk
                root = Tk()
                root.withdraw()  # 隐藏主窗口
                messagebox.showerror("错误", f"缺少必要的库: {', '.join(missing_libraries)}\n\n请安装所需库后重试")
                root.destroy()
                sys.exit(1)
            except:
                print(f"缺少必要的库: {', '.join(missing_libraries)}")
                sys.exit(1)
        
        # 仅在非打包模式下检查pdf2image和poppler
        try:
            from pdf2image import convert_from_bytes
            # 创建一个最小的PDF用于测试
            test_pdf = b"%PDF-1.7\n1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n2 0 obj\n<</Type/Pages/Kids[3 0 R]/Count 1>>\nendobj\n3 0 obj\n<</Type/Page/MediaBox[0 0 3 3]>>\nendobj\nxref\n0 4\n0000000000 65535 f\n0000000010 00000 n\n0000000053 00000 n\n0000000102 00000 n\ntrailer\n<</Size 4/Root 1 0 R>>\nstartxref\n149\n%%EOF"
            convert_from_bytes(test_pdf, dpi=72, size=(10, 10))
        except Exception as e:
            # 非打包模式下显示警告但不阻止启动
            print(f"pdf2image配置警告: {str(e)}")
    
    # 启动主程序
    try:
        # 创建主窗口但初始不可见
        root = tk.Tk()
        # 立即将窗口隐藏，直到完全准备好
        root.withdraw()
        app = PDFSignatureTool(root)
        root.mainloop()
    except Exception as e:
        try:
            from tkinter import messagebox
            messagebox.showerror("错误", f"启动程序时发生错误: {str(e)}\n请检查系统配置后重试")
        except:
            pass
        sys.exit(1)