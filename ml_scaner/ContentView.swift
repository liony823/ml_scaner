//
//  ContentView.swift
//  ml_scaner
//
//  Created by Yh Y on 2025/1/11.
//

import SwiftUI
import CoreML
import AVFoundation
import UIKit

struct ContentView: View {
    @StateObject private var serialManager = SerialPortManager()
    @StateObject private var detectionManager = DetectionManager()
    @State private var showingCamera = false
    @State private var capturedImage: UIImage?
    @State private var logs: [LogMessage] = []
    
    var body: some View {
        VStack {

            if let image = capturedImage {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFit()
                    .frame(maxHeight: 300)
            }
            
            connectButton
            
            // 日志显示框
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(logs) { log in
                        LogMessageView(message: log)
                    }
                }
                .padding()
            }
            .frame(maxWidth: .infinity)
            .background(Color(.systemGray6))
            .cornerRadius(8)
            .padding()
        }
        .onAppear {
            setupManagers()
            setupNotifications()
        }
        .fullScreenCover(isPresented: $showingCamera) {
            CameraView(
                image: $capturedImage,
                isShown: $showingCamera,
                onImageCaptured: handleImageCaptured
            )
        }
    }
    
    private var connectButton: some View {
        Button(serialManager.isConnected ? "断开连接" : "连接服务器") {
            if serialManager.isConnected {
                serialManager.disconnect()
            } else {
                serialManager.connect()
            }
        }
        .padding()
        .buttonStyle(.bordered)
    }
    
    
    private func setupManagers() {
        let logCallback: (String) -> Void = { message in
            addLog(message)
        }
        
        DispatchQueue.main.async {
            self.serialManager.onLog = logCallback
            self.detectionManager.onLog = logCallback
            
            self.serialManager.onBarcodeReceived = { boardId in
                self.addLog("收到开始检测信号，ID: \(boardId)");
                self.detectionManager.currentBoardId = boardId
                self.detectionManager.startCamera()
            }
            
            self.detectionManager.onDetectionComplete = {
//                self.addLog("检测完成: \(hasDefect ? "有缺陷" : "无缺陷")")
                self.detectionManager.sendDetectionResult()
            }
        }
    }
    
    private func setupNotifications() {
        NotificationCenter.default.addObserver(
            forName: .startCamera,
            object: nil,
            queue: .main
        ) { _ in
            showingCamera = true
        }
    }
    
    private func handleImageCaptured(_ image: UIImage) {
        detectionManager.processImage(image)
        // 延迟1秒后发送放行信号
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            serialManager.sendReleaseSignal()
        }
    }
    
    private func addLog(_ message: String) {
        let log = LogMessage(message: message)
        DispatchQueue.main.async {
            logs.append(log)
            // 保持最新的100条日志
            if logs.count > 100 {
                logs.removeFirst(logs.count - 100)
            }
        }
    }
}

struct LogMessage: Identifiable {
    let id = UUID()
    let timestamp = Date()
    let message: String
}

struct LogMessageView: View {
    let message: LogMessage
    
    var body: some View {
        Text("\(timeString) \(message.message)")
            .font(.system(.caption, design: .monospaced))
    }
    
    private var timeString: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm:ss.SSS"
        return formatter.string(from: message.timestamp)
    }
}

// 相机视图
struct CameraView: UIViewControllerRepresentable {
    @Binding var image: UIImage?
    @Binding var isShown: Bool
    let onImageCaptured: (UIImage) -> Void
    
    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.delegate = context.coordinator
        picker.sourceType = .camera
        picker.showsCameraControls = false  // 隐藏相机控制按钮
        
        // 延迟一秒后自动拍照
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            picker.takePicture()
        }
        
        return picker
    }
    
    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}
    
    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }
    
    class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let parent: CameraView
        
        init(_ parent: CameraView) {
            self.parent = parent
            super.init()
        }
        
        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey : Any]) {
            if let image = info[.originalImage] as? UIImage {
                parent.image = image
                parent.onImageCaptured(image)
            }
            parent.isShown = false
        }
        
        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            parent.isShown = false
        }
    }
}

#Preview {
    ContentView()
}


