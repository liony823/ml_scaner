import Foundation
import SocketIO

class SerialPortManager: NSObject, ObservableObject {
    @Published var isConnected = false
    @Published var onLog: ((String) -> Void)?
    @Published var onBarcodeReceived: ((String) -> Void)?
    
    private let manager: SocketManager
    private var socket: SocketIOClient
    
    override init() {
        manager = SocketManager(socketURL: URL(string: "http://192.168.1.227:8080")!, config: [.log(true)])
        socket = manager.defaultSocket
        
        super.init()
        setupSocket()
    }
    
    private func setupSocket() {
        // 监听连接状态
        socket.on(clientEvent: .connect) { [weak self] _, _ in
            self?.log("Socket连接成功")
            DispatchQueue.main.async {
                self?.isConnected = true
            }
        }
        
        socket.on(clientEvent: .disconnect) { [weak self] _, _ in
            self?.log("Socket断开连接")
            DispatchQueue.main.async {
                self?.isConnected = false
            }
        }
        
        socket.on(clientEvent: .error) { [weak self] data, _ in
            if let error = data[0] as? String {
                self?.log("Socket错误: \(error)")
            }
        }
        
        socket.on(clientEvent: .reconnect) { [weak self] _, _ in
            self?.log("Socket正在重新连接...")
        }
        
        socket.on(clientEvent: .reconnectAttempt) { [weak self] _, _ in
            self?.log("Socket尝试重新连接...")
        }
        
        // 监听开始检测信号
        socket.on("start_detection") { [weak self] data, _ in
            if let dict = data[0] as? [String: String],
               dict["message"] == "START" {
                self?.log("收到开始检测信号")
                DispatchQueue.main.async {
                    self?.onBarcodeReceived?("TRIGGER_PHOTO")
                }
            }
        }
    }
    
    private func log(_ message: String) {
        DispatchQueue.main.async {
            self.onLog?(message)
        }
    }
    
    func connect() {
        if !isConnected {
            log("正在连接服务器...")
            socket.connect()
        }
    }
    
    func disconnect() {
        if isConnected {
            log("正在断开服务器连接...")
            socket.disconnect()
            
            // 确保状态更新
            DispatchQueue.main.async {
                self.isConnected = false
            }
        }
    }
    
    func sendReleaseSignal() {
        if isConnected {
            socket.emit("release_signal", ["message": "RELEASE"])
            log("发送放行信号")
        } else {
            log("未连接到服务器，无法发送放行信号")
        }
    }
    
    deinit {
        socket.disconnect()
    }
} 
