import Foundation
import UIKit
import CoreML
import Vision
import AVFoundation

@available(macOS 12.0, iOS 15.0, tvOS 15.0, watchOS 8.0, visionOS 1.0, *)
class DetectionManager: ObservableObject {
    @Published var previewImage: UIImage?
    var currentBoardId: String = ""
    
    var onLog: ((String) -> Void)?
    var onDetectionComplete: ((Bool) -> Void)?
    
    init() {
        log("初始化检测管理器")
    }
    
    func startCamera() {
        log("开始拍照流程")
        
        DispatchQueue.main.async {
            self.log("发送startCamera通知")
            NotificationCenter.default.post(name: .startCamera, object: nil)
        }
    }
    
    func processImage(_ image: UIImage) {
        previewImage = image
        log("开始分析图片")
        
        guard let cgImage = image.cgImage else {
            log("无法获取图像数据")
            return
        }
        
        do {
            let input = try primer_modelInput(
                imageWith: cgImage,
                iouThreshold: 0.5,
                confidenceThreshold: 0.3
            )
            
            let model = try primer_model()
            let prediction = try model.prediction(input: input)
            
            let boxes = prediction.nmsed_pred_boxesShapedArray
            let scores = prediction.nmsed_pred_scoresShapedArray
            
            var hasDefect = false
            var resultDescription = ""
            let detectionCount = scores.shape[0]
            
            if detectionCount > 0 {
                for i in 0..<detectionCount {
                    guard let score = scores[i].scalar,
                          let x1 = boxes[i, 0].scalar,
                          let y1 = boxes[i, 1].scalar,
                          let x2 = boxes[i, 2].scalar,
                          let y2 = boxes[i, 3].scalar else {
                        continue
                    }
                    
                    if score > 0.3 {
                        hasDefect = true
                        resultDescription += String(
                            format: "发现缺陷(置信度: %.1f%%, 位置: [%.2f, %.2f, %.2f, %.2f]) ",
                            score * 100,
                            x1, y1, x2, y2
                        )
                    }
                }
            }
            
            DispatchQueue.main.async {
                self.onDetectionComplete?(hasDefect)
                self.log(resultDescription.isEmpty ? "未检测到明显缺陷" : resultDescription)
            }
            
        } catch {
            log("图像处理失败: \(error)")
        }
    }
    
    func sendDetectionResult(hasDefect: Bool) {
        guard let image = previewImage else {
            log("没有图片可发送")
            return
        }
        
        guard let imageData = image.jpegData(compressionQuality: 0.8) else {
            log("图片压缩失败")
            return
        }
        
        let base64String = imageData.base64EncodedString()
        
        let parameters: [String: Any] = [
            "has_defect": hasDefect,
            "board_id": currentBoardId,
            "image": base64String
        ]
        
        guard let url = URL(string: Constants.Server.detectionResultURL) else {
            log("无效的URL")
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: parameters)
        } catch {
            log("JSON序列化失败: \(error.localizedDescription)")
            return
        }
        
        log("发送检测结果到服务器")
        
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            if let error = error {
                self?.log("发送失败: \(error.localizedDescription)")
                return
            }
            
            if let httpResponse = response as? HTTPURLResponse {
                self?.log("服务器响应状态码: \(httpResponse.statusCode)")
            }
            
            if let data = data,
               let responseString = String(data: data, encoding: .utf8) {
                self?.log("服务器响应: \(responseString)")
            }
        }.resume()
    }
    
    private func log(_ message: String) {
        onLog?(message)
    }
}

struct DetectionResult: Codable {
    let message: String
    let result: String
}

// 添加通知名称
extension Notification.Name {
    static let startCamera = Notification.Name("startCamera")
}
