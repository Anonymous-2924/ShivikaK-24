// Boardroom desktop entry point (Tauri 2). The game itself is the web app in
// ../dist; this is a thin native wrapper.

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .run(tauri::generate_context!())
        .expect("error while running Boardroom");
}
