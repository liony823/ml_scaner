import os
import time
import threading
from logger_config import get_logger

class InputFileMonitor:
    def __init__(self, file_path):
        """初始化文件监控器"""
        self.file_path = file_path
        self.last_modified = 0
        self.is_running = False
        self.monitor_thread = None
        self.last_size = 0
        self.last_content = ""
        self.logger = get_logger("FileMonitor")
        # 添加线程锁保护共享状态
        self.state_lock = threading.Lock()
        self.thread_lock = threading.Lock()
        self.running_lock = threading.Lock()
        self.file_lock = threading.Lock()
    
    def start_monitoring(self, callback_func):
        """开始监控文件"""
        # 使用锁保护运行状态变更
        with self.running_lock:
            was_running = self.is_running
            self.is_running = True
            
            if was_running:
                self.logger.info("监控已经在运行中，忽略重复启动请求")
                return
        
        # 使用锁保护状态数据
        with self.state_lock:
            # 只有初次启动时才重置这些值，保持状态连续性
            if self.last_modified == 0 and self.last_size == 0 and self.last_content == "":
                self.last_modified = 0
                self.last_size = 0
                self.last_content = ""
                self.logger.info("初次启动监控，重置文件状态")
            else:
                self.logger.info(f"继续监控文件，保留上次状态。上次大小: {self.last_size}, 上次内容长度: {len(self.last_content)}")
        
        # 使用锁保护线程管理
        with self.thread_lock:
            if self.monitor_thread is not None and self.monitor_thread.is_alive():
                self.logger.info("监控线程已存在且活跃，不创建新线程")
            else:
                if self.monitor_thread is not None:
                    self.logger.info("清理旧的监控线程引用")
                    self.monitor_thread = None
                    
                self.monitor_thread = threading.Thread(target=self._monitor_loop, args=(callback_func,))
                self.monitor_thread.daemon = True
                self.monitor_thread.start()
                self.logger.info(f"创建并启动新的监控线程: {self.monitor_thread.name}")
        
        self.logger.info(f"开始监控文件: {self.file_path}")
    
    def stop_monitoring(self):
        """停止监控文件，但保留文件状态数据"""
        # 使用锁保护运行状态变更
        with self.running_lock:
            was_running = self.is_running
            self.is_running = False
            
            if not was_running:
                self.logger.info("监控已经停止，忽略重复停止请求")
                return
        
        # 使用锁保护线程管理
        thread_to_join = None
        with self.thread_lock:
            if self.monitor_thread and self.monitor_thread.is_alive():
                if self.monitor_thread == threading.current_thread():
                    self.logger.warning("尝试在监控线程自身中停止监控，跳过等待步骤")
                    # 不执行join操作，只清理引用
                    self.monitor_thread = None
                    self.logger.info("监控线程引用已清理")
                    return
                else:
                    thread_to_join = self.monitor_thread
        
        # 在锁外等待线程终止，避免死锁
        if thread_to_join:
            self.logger.info(f"等待监控线程 {thread_to_join.name} 终止...")
            try:
                thread_to_join.join(timeout=2)
                # 检查线程是否真正终止
                if thread_to_join.is_alive():
                    self.logger.warning("监控线程未能在指定时间内终止，可能存在资源泄漏")
                else:
                    self.logger.info("监控线程已成功终止")
            except Exception as e:
                self.logger.error(f"等待监控线程终止时出错: {e}", exc_info=True)
            

        
        # 清理线程引用
        with self.thread_lock:
            if self.monitor_thread == thread_to_join:
                self.monitor_thread = None
        
        # 记录当前状态数据
        with self.state_lock:
            self.logger.info(f"文件监控已暂停，保留状态数据。当前文件大小: {self.last_size}, 当前内容长度: {len(self.last_content)}")
    
    def _monitor_loop(self, callback_func):
        """监控循环"""
        self.logger.info(f"监控线程 {threading.current_thread().name} 开始运行")
        while True:
            # 检查是否应该继续运行
            with self.running_lock:
                if not self.is_running:
                    self.logger.info(f"监控线程 {threading.current_thread().name} 检测到停止信号，退出循环")
                    break
                
            try:
                # 线程安全地检查文件状态
                if os.path.exists(self.file_path):
                    try:
                        current_modified = os.path.getmtime(self.file_path)
                        current_size = os.path.getsize(self.file_path)
                    except (FileNotFoundError, PermissionError) as e:
                        self.logger.error(f"获取文件信息出错: {e}")
                        time.sleep(0.5)
                        continue
                    
                    # 使用锁保护状态比较
                    need_process = False
                    with self.state_lock:
                        if (current_modified > self.last_modified or current_size != self.last_size) and current_size > 0:
                            need_process = True
                            self.last_modified = current_modified
                    
                    if need_process:
                        try:
                            # 处理文件
                            self._process_file(callback_func)
                        except Exception as e:
                            self.logger.error(f"处理文件出错: {e}", exc_info=True)
                
                time.sleep(0.5)  # 每0.5秒检查一次
            except Exception as e:
                self.logger.error(f"监控循环出错: {e}", exc_info=True)
                time.sleep(1)  # 错误后稍微延长等待时间
        
        self.logger.info(f"监控线程 {threading.current_thread().name} 已退出")
    
    def _process_file(self, callback_func):
        """处理文件内容，只读取新增的内容"""
        current_content = ""
        current_size = 0
        
        # 使用文件锁保护文件读取
        with self.file_lock:
            try:
                # 读取文件当前全部内容
                with open(self.file_path, 'r', encoding='utf-8') as file:
                    current_content = file.read()
                
                current_size = os.path.getsize(self.file_path)
            except (FileNotFoundError, PermissionError, IOError) as e:
                self.logger.error(f"读取文件出错: {e}")
                return
        
        # 确定新增内容
        new_content = ""
        
        # 使用锁保护状态访问和更新
        with self.state_lock:
            # 计算新增内容
            if not self.last_content:
                # 如果没有上次内容记录（首次读取），使用整个内容
                self.logger.info("首次读取，使用全部内容")
                new_content = current_content
            elif current_size < self.last_size:
                # 如果文件变小了（可能被清空或部分删除），也使用整个内容
                self.logger.info("文件大小减少，使用全部内容")
                new_content = current_content
            elif current_size > self.last_size:
                # 正常情况：文件增大，只读取新增部分
                self.logger.info("文件增大，只读取新增部分")
                new_content = current_content[len(self.last_content):]
            else:
                # 文件大小相同但内容可能发生变化，检查内容是否有变化
                if current_content != self.last_content:
                    self.logger.info("文件大小相同但内容发生变化，使用全部内容")
                    new_content = current_content
                else:
                    self.logger.info("文件内容未变化，无需处理")
                    new_content = ""
            
            # 更新状态
            self.last_content = current_content
            self.last_size = current_size
        
        # 处理新增内容：移除所有空格和换行符
        if new_content:
            processed_content = ''.join(new_content.split())
            
            if processed_content:
                self.logger.info(f"读取到内容: {processed_content}")
                
                # 安全调用回调函数
                try:
                    callback_func(processed_content)
                except Exception as e:
                    self.logger.error(f"调用回调函数出错: {e}", exc_info=True)
            else:
                self.logger.info("内容经处理后为空，不调用回调函数")
        else:
            self.logger.warning("没有检测到新内容")