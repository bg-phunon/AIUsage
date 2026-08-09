import Foundation

let freshLimit: TimeInterval = 180
let staleLimit: TimeInterval = 1800
let wakeGrace: TimeInterval = 90

enum Freshness: Equatable {
    case fresh
    case stale
    case dead
}

enum Certainty: Equatable {
    case exact
    case atLeast
    case unknown
}

func freshness(snapshotAge: TimeInterval?, wokeRecently: Bool) -> Freshness {
    guard let age = snapshotAge else { return .dead }
    if wokeRecently { return .fresh }
    if age < freshLimit { return .fresh }
    if age < staleLimit { return .stale }
    return .dead
}

func certainty(confidence: String?) -> Certainty {
    switch confidence {
    case "valid", "zero": return .exact
    case "lower_bound": return .atLeast
    default: return .unknown
    }
}

func ageText(_ seconds: TimeInterval) -> String {
    let value = max(0, Int(seconds))
    if value < 60 { return "\(value)s" }
    if value < 3600 { return "\(value / 60)m" }
    if value < 86400 { return "\(value / 3600)h" }
    return "\(value / 86400)d"
}
