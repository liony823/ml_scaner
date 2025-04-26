from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
import base64
from datetime import datetime
import logging
import threading
import serial
import serial.tools.list_ports
import time
from pathlib import Path
from file_monitor import InputFileMonitor
from logger_config import setup_logging, get_logger

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 设置日志目录
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# 初始化日志配置
setup_logging(LOGS_DIR)
logger = get_logger("Server")

INPUT_FILE = BASE_DIR / "input" / "input.txt"
if not INPUT_FILE.exists():
    INPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    INPUT_FILE.touch()

IMAGES_OK_DIR = BASE_DIR / 'Images' / 'OK'
IMAGES_NG_DIR = BASE_DIR / 'Images' / 'NG'

for dir_path in [IMAGES_OK_DIR, IMAGES_NG_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# 创建单一的文件监控器实例
# 文件监控器实例
last_instance_id = 0
file_monitor = None
# 添加监控器锁，保护对file_monitor的并发访问
monitor_lock = threading.Lock()

# 当收到文件内容时的回调函数
def on_file_content(content):
    try:
        logger.info(f"读取到文件内容: {content}")
        # 发送开始检测的信号
        socketio.emit('start_detection', {'message': 'START', 'data': content})

        def safe_stop():
            logger.info("在新线程中安全停止文件监控")
            stop_file_monitoring()
            
        stop_thread = threading.Thread(target=safe_stop)
        stop_thread.daemon = True
        stop_thread.start()
        logger.info(f"已创建停止线程: {stop_thread.name}")
    except Exception as e:
        logger.error(f"发送信号时出错: {e}", exc_info=True)

    # def delayed_stop():
    #     logger.info("计划延迟停止文件监控")
    #     stop_file_monitoring()
    
    # # 使用线程延迟停止监控
    # timer = threading.Timer(0.1, delayed_stop)
    # timer.daemon = True
    # timer.start()

def start_file_monitoring():
    global file_monitor, last_instance_id
    current_id = id(file_monitor) if file_monitor else 0
    
    logger.info(f"启动文件监控 - 当前实例ID: {current_id}, 上次记录ID: {last_instance_id}")

    with monitor_lock:
        if file_monitor is None:
            logger.info("创建新的文件监控器实例")
            file_monitor = InputFileMonitor(str(INPUT_FILE))
            last_instance_id = id(file_monitor)
        elif current_id != last_instance_id and last_instance_id != 0:
            logger.warning(f"实例ID变化 ({last_instance_id} -> {current_id}")
            # 记录新实例ID但不重新创建
            last_instance_id = current_id
            
        file_monitor.start_monitoring(on_file_content)
        logger.info("文件监控已启动")

def stop_file_monitoring():
    logger.info("请求停止文件监控")
    global file_monitor
    with monitor_lock:
        if file_monitor:
            file_monitor.stop_monitoring()
            logger.info("文件监控已停止")

class PLCManager:
    def __init__(self, port=None, baudrate=9600):
        self.serial_port = None
        self.running = False
        self.read_thread = None
        
        # 尝试自动查找可用的COM端口
        if port is None:
            self.auto_connect(baudrate)
        else:
            self.connect(port, baudrate)


    def auto_connect(self, baudrate=9600):
        """自动查找并连接PLC设备"""
        logger.info("开始自动查找PLC设备...")

        
        available_ports = list(serial.tools.list_ports.comports())
        if not available_ports:
            logger.error("未找到任何COM端口设备")
            return False
        
        logger.info(f"发现以下COM端口: {[port.device for port in available_ports]}")
        
        # 尝试连接每个可用端口
        for port_info in available_ports:
            port = port_info.device
            logger.info(f"尝试连接端口: {port}")
            try:
                if self.connect(port, baudrate):
                    logger.info(f"成功连接到PLC设备，端口: {port}")
                    return True
            except Exception as e:
                logger.warning(f"尝试连接端口 {port} 失败: {e}")
                continue
        
        logger.error("无法找到可用的PLC设备")
        return False

    def connect(self, port, baudrate=9600):
        """连接到指定的COM端口"""
        logger.info(f"尝试连接PLC - 端口: {port}, 波特率: {baudrate}")
        try:
            self.serial_port = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=8,
                parity='N',
                stopbits=2,
                timeout=1
            )
            self.running = True
            self.read_thread = threading.Thread(target=self._read_plc)
            self.read_thread.daemon = True  # 设置为守护线程，主程序退出时自动结束
            self.read_thread.start()
            logger.info("PLC连接初始化成功")
            return True
        except Exception as e:
            logger.error(f"PLC连接初始化失败: {e}")
            return False

    def _read_plc(self):
        """持续读取PLC信号"""
        while self.running:
            try:
                if self.serial_port.in_waiting:
                    data = self.serial_port.read(self.serial_port.in_waiting)
                    logger.info(f"收到PLC信号: {data}")
                    logger.info(f"PLC信号长度: {len(data)}")
                    if data:
                        if b'7' in data:
                            logging.info("检测到'7'信号，开始监控文件以获取检测内容")
                            # 启动文件监控来读取input.txt
                            start_file_monitoring()
            except Exception as e:
                logger.error(f"读取PLC数据错误: {e}", exc_info=True)
            time.sleep(0.1)

    def send_command(self, command):
        logger.info(f"发送PLC命令: {command.hex()}")
        try:
            self.serial_port.write(command)
            response = self.serial_port.read(7)
            logger.info(f"PLC响应: {response.hex()}")
            return response
        except Exception as e:
            logger.error(f"PLC通信错误: {e}", exc_info=True)
            raise
    
    def close(self):
        logger.info("关闭PLC连接")
        self.running = False
        if self.read_thread and self.read_thread.is_alive():
            self.read_thread.join()
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()

# 初始化PLC管理器
try:
    plc_manager = PLCManager()
    logger.info("PLC管理器初始化成功")
except Exception as e:
    logger.error(f"PLC管理器初始化失败: {e}", exc_info=True)
    plc_manager = None

@app.route('/detection_result', methods=['POST'])
def receive_detection_result():
    try:
        data = request.json
        # has_defect = data.get('has_defect', False)
        board_id = data.get('board_id', '')
        image_base64 = data.get('image', '')
        
        # logger.info(f"收到检测结果: {'有缺陷' if has_defect else '无缺陷'}")
        
        # 保存图片
        if image_base64:
            try:
                image_data = base64.b64decode(image_base64)
                
                save_dir = IMAGES_OK_DIR
                filename = f"{board_id}.jpg"
                filepath = save_dir / filename
                
                with open(filepath, 'wb') as f:
                    f.write(image_data)
                logger.info(f"图片已保存: {filepath}")
                
                # # 发送不同的PLC信号
                # if plc_manager:
                #     try:
                #         if has_defect:
                #             # NG信号
                #             command = bytes([8])
                #         else:
                #             # OK信号
                #             command = bytes([8])
                        
                #         plc_manager.send_command(command)
                #         logger.info(f"已发送{'NG' if has_defect else 'OK'}信号到PLC")
                #     except Exception as e:
                #         logger.error(f"发送PLC信号失败: {e}", exc_info=True)
                
            except Exception as e:
                logger.error(f"保存图片失败: {str(e)}", exc_info=True)
        
        return jsonify({
            'message': 'Success',
            'result': 'defect' if has_defect else 'normal'
        })
        
    except Exception as e:
        logger.error(f"处理检测结果时出错: {str(e)}", exc_info=True)
        return jsonify({
            'message': 'Error',
            'error': str(e)
        }), 500

@socketio.on('connect')
def handle_connect():
    logger.info('客户端已连接')
    emit('connection_response', {'message': 'Connected'})

@socketio.on('disconnect')
def handle_disconnect():
    logger.info('客户端已断开连接')

@socketio.on('release_signal')
def handle_release_signal(data):
    message = data.get('message', '')
    logger.info(f'收到放行信号: {message}')
    
    # # 发送放行信号到PLC
    # if plc_manager:
    #     try:
    #         release_command = bytes([8])
    #         plc_manager.send_command(release_command)
    #         logger.info("已发送PLC放行信号")
    #     except Exception as e:
    #         logger.error(f"发送PLC放行信号失败: {e}", exc_info=True)

if __name__ == '__main__':
    try:
        logger.info("启动服务器...")
        socketio.run(app, host='0.0.0.0', port=8080, debug=True)
    finally:
        stop_file_monitoring()
        if plc_manager:
            plc_manager.close()