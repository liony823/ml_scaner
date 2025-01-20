from flask import Flask, request, jsonify
from datetime import datetime
import io
import logging
from pathlib import Path
import threading
import time
import socketio
import base64
from PIL import Image

app = Flask(__name__)
sio = socketio.Server(cors_allowed_origins='*')
app.wsgi_app = socketio.WSGIApp(sio, app.wsgi_app)

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


LOGS_DIR = BASE_DIR / 'logs'
IMAGES_OK_DIR = BASE_DIR / 'Images' / 'OK'
IMAGES_NG_DIR = BASE_DIR / 'Images' / 'NG'

for dir_path in [LOGS_DIR, IMAGES_OK_DIR, IMAGES_NG_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

class MockPLCManager:
    """模拟PLC管理器，用于测试"""
    def __init__(self):
        logging.info("初始化模拟PLC连接")
        self.running = True
        self.test_thread = threading.Thread(target=self._simulate_plc_signal)
        self.test_thread.start()
    
    def _simulate_plc_signal(self):
        """模拟PLC定期发送检测信号"""
        while self.running:
            time.sleep(20)  # 每5秒发送一次信号
            logging.info("模拟PLC发送检测信号")
            # 通知所有客户端开始拍照
            sio.emit('start_detection', {'message': 'START'})
    
    def send_command(self, command):
        logging.info(f"模拟发送PLC命令: {command.hex()}")
        # 模拟PLC响应
        response = bytes([0x02, 0x06, 0x00, 0x00, 0x00, 0x03, 0x00, 0x00])
        logging.info(f"模拟PLC响应: {response.hex()}")
        return response
    
    def close(self):
        logging.info("关闭模拟PLC连接")
        self.running = False
        if self.test_thread.is_alive():
            self.test_thread.join()

# 初始化PLC管理器
logging.info("初始化系统组件")
try:
    plc_manager = MockPLCManager()
    logging.info("系统组件初始化完成")
except Exception as e:
    logging.error(f"系统初始化失败: {e}")
    raise

@sio.event
def connect(sid, environ):
    logging.info(f"客户端连接: {sid}")

@sio.event
def disconnect(sid):
    logging.info(f"客户端断开: {sid}")

@app.route('/detection_result', methods=['POST'])
def detection_result():
    """接收客户端的检测结果和图片"""
    logging.info("收到检测结果")
    try:
        data = request.json
        has_defect = data.get('has_defect', False)
        image_base64 = data.get('image', '')
        
        # 保存图片
        if image_base64:
            try:
                # 解码base64图片数据
                image_data = base64.b64decode(image_base64)
                image = Image.open(io.BytesIO(image_data))
                
                # 生成文件名和保存路径
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                folder = IMAGES_NG_DIR if has_defect else IMAGES_OK_DIR
                filepath = folder / f"{timestamp}.jpg"
                
                # 保存图片
                image.save(filepath)
                logging.info(f"图片已保存: {filepath}")
            except Exception as e:
                logging.error(f"保存图片失败: {e}")
        else:
            logging.warning("未收到图片数据")
        
        # 发送放行信号
        logging.info("发送放行信号")
        release_command = bytes([0x02, 0x06, 0x00, 0x00, 0x00, 0x03, 0xC9, 0xF8])
        plc_manager.send_command(release_command)
        
        return jsonify({'message': '处理成功'})
    
    except Exception as e:
        logging.error(f"处理过程发生错误: {e}")
        return jsonify({'message': f'处理错误: {str(e)}'}), 500

if __name__ == '__main__':
    logging.info("启动测试服务器")
    try:
        app.run(host='0.0.0.0', port=8080)
    except Exception as e:
        logging.error(f"服务器运行错误: {e}")
    finally:
        logging.info("关闭服务器")
        plc_manager.close()