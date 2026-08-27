use tauri::{App,Runtime,Window};

#[tauri::command]
fn call_ollama_api() -> String {
  // Implement Ollama API integration here
  "Ollama API called".to_string()
}

fn main() {
  tauri::Builder::default()
    .invoke_handler(tauri::generate_handler![call_ollama_api])
    .run(tauri::generate_app_data!("src-tauri/data.json"))
    .expect("error while running tauri app");
}
