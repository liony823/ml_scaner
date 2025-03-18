import Foundation

/// 应用程序全局常量
struct Constants {
    /// 服务器相关常量
    struct Server {
        /// 服务器主机地址
        static let host = "172.20.10.2"
        
        /// 服务器端口
        static let port = 8080
        
        /// 完整的服务器基础URL
        static let baseURL = "http://\(host):\(port)"
        
        /// 检测结果接口URL
        static let detectionResultURL = "\(baseURL)/detection_result"
    }
} 
