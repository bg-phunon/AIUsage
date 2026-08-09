import Foundation

let engineTimeout: TimeInterval = 45

enum EngineError: Error {
    case alreadyRunning
    case timedOut
    case failed(code: Int32, stderr: String)
}

final class EngineRunner {
    private let scriptURL: URL
    private let timeout: TimeInterval
    private let queue = DispatchQueue(label: "com.local.aiusage.engine")
    private var running = false
    private let lock = NSLock()
    private(set) var lastError: String?

    var isRunning: Bool {
        lock.lock(); defer { lock.unlock() }
        return running
    }

    init(scriptURL: URL, timeout: TimeInterval = engineTimeout) {
        self.scriptURL = scriptURL
        self.timeout = timeout
    }

    static var bundledScriptURL: URL? {
        Bundle.main.url(forResource: "ai-usage.60s", withExtension: "py")
    }

    func run(completion: @escaping (Result<Void, EngineError>) -> Void) {
        lock.lock()
        if running {
            lock.unlock()
            completion(.failure(.alreadyRunning))
            return
        }
        running = true
        lock.unlock()

        queue.async { [weak self] in
            guard let self else { return }
            let result = self.execute()
            self.lock.lock()
            self.running = false
            self.lastError = if case .failure(let error) = result { Self.describe(error) } else { nil }
            self.lock.unlock()
            DispatchQueue.main.async { completion(result) }
        }
    }

    private func execute() -> Result<Void, EngineError> {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = ["python3", scriptURL.path, "--snapshot"]
        let errorPipe = Pipe()
        process.standardError = errorPipe
        process.standardOutput = Pipe()

        do {
            try process.run()
        } catch {
            return .failure(.failed(code: -1, stderr: error.localizedDescription))
        }

        let deadline = Date().addingTimeInterval(timeout)
        while process.isRunning && Date() < deadline {
            Thread.sleep(forTimeInterval: 0.1)
        }
        if process.isRunning {
            process.terminate()
            return .failure(.timedOut)
        }

        let data = errorPipe.fileHandleForReading.readDataToEndOfFile()
        let stderr = String(data: data, encoding: .utf8) ?? ""
        if process.terminationStatus != 0 {
            return .failure(.failed(code: process.terminationStatus,
                                    stderr: stderr.trimmingCharacters(in: .whitespacesAndNewlines)))
        }
        return .success(())
    }

    static func describe(_ error: EngineError) -> String {
        switch error {
        case .alreadyRunning: return "รอบก่อนยังไม่จบ"
        case .timedOut: return "engine ค้างเกิน \(Int(engineTimeout)) วินาที"
        case .failed(let code, let stderr):
            let line = stderr.split(separator: "\n").last.map(String.init) ?? ""
            return line.isEmpty ? "engine ออกด้วยรหัส \(code)" : line
        }
    }
}
