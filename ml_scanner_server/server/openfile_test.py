


def on_content_changed(content):
    """当文件内容变化时的回调函数"""
    print("检测到文件内容变化")
    print(f"处理后的内容: {content}")


def main():
    """主函数"""
    # 获取input.txt的绝对路径
    input_file = Path(__file__).parent.parent / "input" / "input.txt"
    
    # 确保文件存在
    if not input_file.exists():
        input_file.parent.mkdir(parents=True, exist_ok=True)
        input_file.touch()
    
    print(f"监控文件路径: {input_file}")
    
    # 创建并启动监控器
    monitor = InputFileMonitor(str(input_file))
    
    try:
        monitor.start_monitoring(on_content_changed)
        
        # 主循环，可以通过键盘中断停止
        print("服务器已启动，按 Ctrl+C 停止...")
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("接收到中断信号，停止服务...")
    finally:
        monitor.stop_monitoring()
        print("服务已停止")


if __name__ == "__main__":
    main()