import AppKit

// Exact file-name filtering, rather than accepting every .keys file.
func isDirectory(_ url: URL) -> Bool {
    var directory: ObjCBool = false
    return FileManager.default.fileExists(atPath: url.path, isDirectory: &directory) && directory.boolValue
}
func isKeyFile(_ url: URL) -> Bool {
    url.isFileURL && FileManager.default.fileExists(atPath: url.path) && !isDirectory(url) && url.lastPathComponent == "prod.keys"
}
let language = Locale.preferredLanguages.first ?? "en"
let traditional = language.contains("Hant") || language.contains("TW") || language.contains("HK") || language.contains("MO")
let heading: String
let detail: String
let button: String
if language.hasPrefix("zh") {
    heading = traditional ? "第 2/3 步：選擇 prod.keys" : "第 2/3 步：选择 prod.keys"
    detail = traditional ? "只能選擇名為 prod.keys 的密鑰檔案；不是資料夾，也不是 title.keys。" : "只能选择名为 prod.keys 的密钥文件；不是文件夹，也不是 title.keys。"
    button = traditional ? "使用此密鑰" : "使用此密钥"
} else {
    heading = "Step 2/3: Select prod.keys"
    detail = "Select the file named prod.keys, not a folder or title.keys. Other files are disabled."
    button = "Use this key file"
}
final class KeySelectionDelegate: NSObject, NSOpenSavePanelDelegate {
    func panel(_ sender: Any, shouldEnable url: URL) -> Bool {
        isDirectory(url) || isKeyFile(url)
    }
    func panel(_ sender: Any, validate url: URL) throws {
        guard isKeyFile(url) else {
            throw NSError(domain: "NXOneClickKeys", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: detail])
        }
    }
}
// Exercise the actual delegate without displaying a panel or reading key contents.
if CommandLine.arguments.dropFirst().first == "--test-filter" {
    let delegate = KeySelectionDelegate()
    var results: [[String: Any]] = []
    for path in CommandLine.arguments.dropFirst(2) {
        let url = URL(fileURLWithPath: path)
        var valid = true
        do { try delegate.panel(NSNull(), validate: url) } catch { valid = false }
        results.append(["name": url.lastPathComponent,
                        "enabled": delegate.panel(NSNull(), shouldEnable: url), "valid": valid])
    }
    let data = try JSONSerialization.data(withJSONObject: results, options: [.sortedKeys])
    print(String(decoding: data, as: UTF8.self))
    exit(0)
}
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let panel = NSOpenPanel()
panel.title = heading
panel.message = detail
panel.prompt = button
panel.canChooseFiles = true
panel.canChooseDirectories = false
panel.allowsMultipleSelection = false
let delegate = KeySelectionDelegate()
panel.delegate = delegate
app.activate(ignoringOtherApps: true)
let response = withExtendedLifetime(delegate) { panel.runModal() }
if response == .OK, let url = panel.url, isKeyFile(url) {
    print(url.path)
} else {
    exit(130)
}
