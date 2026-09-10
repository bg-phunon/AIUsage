import Foundation

let engineTimeout: TimeInterval = 45

enum EngineError: Error {
    case alreadyRunning
    case timedOut
    case pythonMissing
    case failed(code: Int32, stderr: String)
}

final class EngineRunner {
    private let scriptURL: URL
    private let liveUsage: () -> Bool?
    private let python: () -> String?
    private let timeout: TimeInterval
    private let queue = DispatchQueue(label: "com.local.aiusage.engine")
    private var running = false
    private let lock = NSLock()
    private(set) var lastError: String?

    var isRunning: Bool {
        lock.lock(); defer { lock.unlock() }
        return running
    }

    init(scriptURL: URL,
         liveUsage: @escaping () -> Bool? = { nil },
         python: @escaping () -> String? = { findPython() },
         timeout: TimeInterval = engineTimeout) {
        self.scriptURL = scriptURL
        self.liveUsage = liveUsage
        self.python = python
        self.timeout = timeout
    }

    /// ถามใหม่ทุกครั้งที่รัน ไม่จำไว้ตอนสร้าง — คนที่เพิ่ง `brew install python`
    /// เสร็จต้องใช้ได้ทันทีโดยไม่ต้องปิดเปิดแอป
    func resolvedPython() -> String? { python() }

    /// argv ที่ส่งให้เอนจิน — แยกออกมาให้เทสต์อ่านได้โดยไม่ต้อง spawn process
    ///
    /// ไม่มีความเห็น = ไม่ส่ง flag แล้วปล่อยให้ config.json ตัดสิน ซึ่งเป็นทางเดียว
    /// ที่เครื่องซึ่งใช้ live มาก่อนจะไม่ถูกปิดทิ้งเงียบๆ ตอนอัปเดต
    static func arguments(script: String, liveUsage: Bool?) -> [String] {
        var args = [script, "--snapshot"]
        if let liveUsage { args.append("--live-usage=\(liveUsage ? 1 : 0)") }
        return args
    }

    /// สภาพแวดล้อมของ process ลูก — สืบทอดของเดิมทั้งหมด แล้วย้ายที่เก็บ bytecode
    ///
    /// python เขียน __pycache__ ไว้ข้างโมดูลที่ import เสมอ ซึ่งกับแอปที่ติดตั้งแล้ว
    /// แปลว่ามันเขียนไฟล์ลงใน .app ของตัวเองทุกครั้งที่รัน ลายเซ็นเสียและของชั่วคราว
    /// ไปกองอยู่ใน /Applications · ย้ายที่เก็บดีกว่าปิด cache ทิ้ง เพราะปิดแล้ว
    /// เอนจินจะถูกคอมไพล์ใหม่ทุก 60 วินาทีไปตลอด
    static func environment() -> [String: String] {
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPYCACHEPREFIX"] = NSString(string: "~/Library/Caches/AIUsage/pycache")
            .expandingTildeInPath
        return env
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
        guard let interpreter = resolvedPython() else { return .failure(.pythonMissing) }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: interpreter)
        process.arguments = Self.arguments(script: scriptURL.path, liveUsage: liveUsage())
        process.environment = Self.environment()
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
        case .pythonMissing:
            return "ไม่พบ python3 ในเครื่อง — ลง(ใหม่)ด้วย brew install python"
        case .failed(let code, let stderr):
            let line = stderr.split(separator: "\n").last.map(String.init) ?? ""
            return line.isEmpty ? "engine ออกด้วยรหัส \(code)" : line
        }
    }
}
