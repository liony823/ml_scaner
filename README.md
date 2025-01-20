安装 Pyhton 环境

cd ml_scanner_server

python -m venv venv

source venv/bin/activate

pip install -r  requirements.txt

无plc连接时测试
python server_test.py

正式环境
python server.py