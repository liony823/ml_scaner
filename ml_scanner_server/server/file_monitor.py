import os
import time
import threading

class InputFileMonitor:
    def __init__(self, file_path):
        """初始化文件监控器"""
        self.file_path = file_path
        self.last_modified = 0
        self.is_running = False
        self.monitor_thread = None
    
    def start_monitoring(self, callback_func):
        """开始监控文件"""
        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, args=(callback_func,))
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        print(f"开始监控文件: {self.file_path}")
    
    def stop_monitoring(self):
        """停止监控文件"""
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1)
        print("文件监控已停止")
    
    def _monitor_loop(self, callback_func):
        """监控循环"""
        while self.is_running:
            try:
                if os.path.exists(self.file_path):
                    current_modified = os.path.getmtime(self.file_path)
                    
                    # 检查文件是否被修改且不为空
                    if current_modified > self.last_modified and os.path.getsize(self.file_path) > 0:
                        self.last_modified = current_modified
                        self._process_file(callback_func)
                        
                time.sleep(0.5)  # 每0.5秒检查一次
            except Exception as e:
                print(f"监控过程中出错: {e}")
    
    def _process_file(self, callback_func):
        """处理文件内容"""
        try:
            # 读取文件内容
            with open(self.file_path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            # 处理内容：移除所有空格和换行符
            processed_content = ''.join(content.split())
            
            # 清空文件
            with open(self.file_path, 'w', encoding='utf-8') as file:
                file.write('')
            
            # 调用回调函数处理结果
            callback_func(processed_content)
            
        except Exception as e:
            print(f"处理文件时出错: {e}")