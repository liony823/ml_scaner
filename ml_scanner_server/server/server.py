from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
import base64
import os
from datetime import datetime
import logging
import threading
import serial
import time
from pathlib import Path

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建图片存储目录
BASE_DIR = Path('Images')
OK_DIR = BASE_DIR / 'OK'
NG_DIR = BASE_DIR / 'NG'

for dir_path in [OK_DIR, NG_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

class PLCManager:
    def __init__(self, port='COM1', baudrate=9600):
        logger.info(f"初始化PLC连接 - 端口: {port}, 波特率: {baudrate}")
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
            self.read_thread.start()
            logger.info("PLC连接初始化成功")
        except Exception as e:
            logger.error(f"PLC连接初始化失败: {e}")
            raise

    def _read_plc(self):
        """持续读取PLC信号"""
        while self.running:
            try:
                if self.serial_port.in_waiting:
                    data = self.serial_port.read(7)
                    if len(data) >= 7:
                        if data[0] == 0x02 and data[1] == 0x03:
                            if data[2] == 0x02 and data[3] == 0x00 and data[4] == 0x02:
                                logger.info("收到PLC检测信号")
                                # 通知所有客户端开始拍照
                                socketio.emit('start_detection', {'message': 'START'})
            except Exception as e:
                logger.error(f"读取PLC数据错误: {e}")
            time.sleep(0.1)

    def send_command(self, command):
        logger.info(f"发送PLC命令: {command.hex()}")
        try:
            self.serial_port.write(command)
            response = self.serial_port.read(7)
            logger.info(f"PLC响应: {response.hex()}")
            return response
        except Exception as e:
            logger.error(f"PLC通信错误: {e}")
            raise
    
    def close(self):
        logger.info("关闭PLC连接")
        self.running = False
        if self.read_thread.is_alive():
            self.read_thread.join()
        self.serial_port.close()

# 初始化PLC管理器
try:
    plc_manager = PLCManager()
    logger.info("PLC管理器初始化成功")
except Exception as e:
    logger.error(f"PLC管理器初始化失败: {e}")
    plc_manager = None

@app.route('/detection_result', methods=['POST'])
def receive_detection_result():
    try:
        data = request.json
        has_defect = data.get('has_defect', False)
        image_base64 = data.get('image', '')
        
        logger.info(f"收到检测结果: {'有缺陷' if has_defect else '无缺陷'}")
        
        # 保存图片
        if image_base64:
            try:
                image_data = base64.b64decode(image_base64)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                
                save_dir = NG_DIR if has_defect else OK_DIR
                filename = f"{timestamp}.jpg"
                filepath = save_dir / filename
                
                with open(filepath, 'wb') as f:
                    f.write(image_data)
                logger.info(f"图片已保存: {filepath}")
                
                # 发送不同的PLC信号
                if plc_manager:
                    try:
                        if has_defect:
                            # NG信号
                            command = bytes([0x02, 0x06, 0x00, 0x00, 0x00, 0x02, 0x09, 0xF8])
                        else:
                            # OK信号
                            command = bytes([0x02, 0x06, 0x00, 0x00, 0x00, 0x01, 0xC9, 0xF8])
                        
                        plc_manager.send_command(command)
                        logger.info(f"已发送{'NG' if has_defect else 'OK'}信号到PLC")
                    except Exception as e:
                        logger.error(f"发送PLC信号失败: {e}")
                
            except Exception as e:
                logger.error(f"保存图片失败: {str(e)}")
        
        return jsonify({
            'message': 'Success',
            'result': 'defect' if has_defect else 'normal'
        })
        
    except Exception as e:
        logger.error(f"处理检测结果时出错: {str(e)}")
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
    
    # 发送放行信号到PLC
    if plc_manager:
        try:
            release_command = bytes([0x02, 0x06, 0x00, 0x00, 0x00, 0x03, 0xC9, 0xF8])
            plc_manager.send_command(release_command)
            logger.info("已发送PLC放行信号")
        except Exception as e:
            logger.error(f"发送PLC放行信号失败: {e}")

if __name__ == '__main__':
    try:
        socketio.run(app, host='0.0.0.0', port=8080, debug=True)
    finally:
        if plc_manager:
            plc_manager.close()