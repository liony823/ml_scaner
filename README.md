安装 Pyhton 环境

cd ml_scanner_server

以下命令 都在ml_scanner_server目录下操作

python -m venv venv

source venv/bin/activate

pip install -r  requirements.txt

无plc连接时测试
python server_test.py

正式环境
python server.py