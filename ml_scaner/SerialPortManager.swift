import Foundation
import SocketIO

class SerialPortManager: NSObject, ObservableObject {
    @Published var isConnected = false
    @Published var onLog: ((String) -> Void)?
    @Published var onBarcodeReceived: ((String) -> Void)?
    
    private let manager: SocketManager
    private var socket: SocketIOClient
    
    override init() {
        // 记录使用的服务器地址
        let serverURL = Constants.Server.baseURL
        
        manager = SocketManager(socketURL: URL(string: serverURL)!, config: [.log(true)])
        socket = manager.defaultSocket
        
        super.init()
        
        log("初始化Socket管理器，服务器地址: \(serverURL)")
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
            } else {
                self?.log("Socket发生未知错误")
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
            self?.log("收到start_detection事件：\(data)")
            
            if let dict = data[0] as? [String: Any] {
                self?.log("事件数据: \(dict)")
                
                if let message = dict["message"] as? String {
                    self?.log("消息字段: \(message)")
                    
                    if message == "START" {
                        let boardId = dict["data"] as? String ?? ""
                        self?.log("成功解析检测信号，ID: \(boardId)")
                        
                        DispatchQueue.main.async {
                            self?.onBarcodeReceived?(boardId)
                        }
                    } else {
                        self?.log("消息不是START: \(message)")
                    }
                } else {
                    self?.log("未找到message字段")
                }
            } else {
                self?.log("无法解析事件数据")
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
