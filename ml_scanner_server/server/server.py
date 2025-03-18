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

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(BASE_DIR / 'logs' / 'server.log'),
        logging.StreamHandler()
    ]
)

INPUT_FILE = BASE_DIR / "input" / "input.txt"
if not INPUT_FILE.exists():
    INPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    INPUT_FILE.touch()
LOGS_DIR = BASE_DIR / 'logs'
IMAGES_OK_DIR = BASE_DIR / 'Images' / 'OK'
IMAGES_NG_DIR = BASE_DIR / 'Images' / 'NG'

for dir_path in [LOGS_DIR, IMAGES_OK_DIR, IMAGES_NG_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# 文件监控器实例
file_monitor = None

# 当收到文件内容时的回调函数
def on_file_content(content):
    logging.info(f"读取到文件内容: {content}")
    # 发送开始检测的信号
    socketio.emit('start_detection', {'message': 'START', 'data': content})
    # 停止文件监控
    if file_monitor:
        file_monitor.stop_monitoring()

def start_file_monitoring():
    global file_monitor
    if file_monitor is None:
        file_monitor = InputFileMonitor(str(INPUT_FILE))
    file_monitor.start_monitoring(on_file_content)

def stop_file_monitoring():
    global file_monitor
    if file_monitor:
        file_monitor.stop_monitoring()
        file_monitor = None

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
        logging.info("开始自动查找PLC设备...")

        
        available_ports = list(serial.tools.list_ports.comports())
        if not available_ports:
            logging.error("未找到任何COM端口设备")
            return False
        
        logging.info(f"发现以下COM端口: {[port.device for port in available_ports]}")
        
        # 尝试连接每个可用端口
        for port_info in available_ports:
            port = port_info.device
            logging.info(f"尝试连接端口: {port}")
            try:
                if self.connect(port, baudrate):
                    logging.info(f"成功连接到PLC设备，端口: {port}")
                    return True
            except Exception as e:
                logging.warning(f"尝试连接端口 {port} 失败: {e}")
                continue
        
        logging.error("无法找到可用的PLC设备")
        return False

    def connect(self, port, baudrate=9600):
        """连接到指定的COM端口"""
        logging.info(f"尝试连接PLC - 端口: {port}, 波特率: {baudrate}")
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
            logging.info("PLC连接初始化成功")
            return True
        except Exception as e:
            logging.error(f"PLC连接初始化失败: {e}")
            return False

    def _read_plc(self):
        """持续读取PLC信号"""
        while self.running:
            try:
                if self.serial_port.in_waiting:
                    data = self.serial_port.read(self.serial_port.in_waiting)
                    logging.info(f"收到PLC信号: {data}")
                    logging.info(f"PLC信号长度: {len(data)}")
                    if data:
                        if b'7' in data:
                            logging.info("检测到'7'信号，开始监控文件以获取检测内容")
                            # 启动文件监控来读取input.txt
                            stop_file_monitoring() 
                            start_file_monitoring()
                            
            except Exception as e:
                logging.error(f"读取PLC数据错误: {e}")
            time.sleep(0.1)

    def send_command(self, command):
        logging.info(f"发送PLC命令: {command.hex()}")
        try:
            self.serial_port.write(command)
            response = self.serial_port.read(7)
            logging.info(f"PLC响应: {response.hex()}")
            return response
        except Exception as e:
            logging.error(f"PLC通信错误: {e}")
            raise
    
    def close(self):
        logging.info("关闭PLC连接")
        self.running = False
        if self.read_thread.is_alive():
            self.read_thread.join()
        self.serial_port.close()

# 初始化PLC管理器
try:
    plc_manager = PLCManager()
    logging.info("PLC管理器初始化成功")
except Exception as e:
    logging.error(f"PLC管理器初始化失败: {e}")
    plc_manager = None

@app.route('/detection_result', methods=['POST'])
def receive_detection_result():
    try:
        data = request.json
        has_defect = data.get('has_defect', False)
        board_id = data.get('board_id', '')
        image_base64 = data.get('image', '')
        
        logging.info(f"收到检测结果: {'有缺陷' if has_defect else '无缺陷'}")
        
        # 保存图片
        if image_base64:
            try:
                image_data = base64.b64decode(image_base64)
                
                save_dir = IMAGES_NG_DIR if has_defect else IMAGES_OK_DIR
                filename = f"{board_id}.jpg"
                filepath = save_dir / filename
                
                with open(filepath, 'wb') as f:
                    f.write(image_data)
                logging.info(f"图片已保存: {filepath}")
                
                # 发送不同的PLC信号
                if plc_manager:
                    try:
                        if has_defect:
                            # NG信号
                            command = bytes([8])
                        else:
                            # OK信号
                            command = bytes([8])
                        
                        plc_manager.send_command(command)
                        logging.info(f"已发送{'NG' if has_defect else 'OK'}信号到PLC")
                    except Exception as e:
                        logging.error(f"发送PLC信号失败: {e}")
                
            except Exception as e:
                logging.error(f"保存图片失败: {str(e)}")
        
        return jsonify({
            'message': 'Success',
            'result': 'defect' if has_defect else 'normal'
        })
        
    except Exception as e:
        logging.error(f"处理检测结果时出错: {str(e)}")
        return jsonify({
            'message': 'Error',
            'error': str(e)
        }), 500

@socketio.on('connect')
def handle_connect():
    logging.info('客户端已连接')
    emit('connection_response', {'message': 'Connected'})

@socketio.on('disconnect')
def handle_disconnect():
    logging.info('客户端已断开连接')

@socketio.on('release_signal')
def handle_release_signal(data):
    message = data.get('message', '')
    logging.info(f'收到放行信号: {message}')
    
    # 发送放行信号到PLC
    if plc_manager:
        try:
            release_command = bytes([8])
            plc_manager.send_command(release_command)
            logging.info("已发送PLC放行信号")
        except Exception as e:
            logging.error(f"发送PLC放行信号失败: {e}")

if __name__ == '__main__':
    try:
        socketio.run(app, host='0.0.0.0', port=8080, debug=True)
    finally:
        # 停止文件监控
        stop_file_monitoring()
        # 停止PLC连接
        if plc_manager:
            plc_manager.close()