mod embeddings;
mod markdown;
mod vault;

use tokio::sync::Mutex;
use tauri::State;
use vault::{FileTreeNode, GraphData, NoteDetail, SearchResult, VaultInfo, VaultManager};

struct AppState {
    vault_manager: Mutex<Option<VaultManager>>,
}

#[tauri::command]
async fn init_manager(state: State<'_, AppState>) -> Result<(), String> {
    let mgr = VaultManager::new().await?;
    let mut lock = state.vault_manager.lock().await;
    *lock = Some(mgr);
    Ok(())
}

#[tauri::command]
async fn list_vaults(state: State<'_, AppState>) -> Result<Vec<VaultInfo>, String> {
    let lock = state.vault_manager.lock().await;
    let mgr = lock.as_ref().ok_or("Manager not initialized")?;
    Ok(mgr.list_vaults())
}

#[tauri::command]
async fn create_vault(
    state: State<'_, AppState>,
    name: String,
    source_path: String,
) -> Result<VaultInfo, String> {
    let mut lock = state.vault_manager.lock().await;
    let mgr = lock.as_mut().ok_or("Manager not initialized")?;
    mgr.create_vault(&name, &source_path).await
}

#[tauri::command]
async fn delete_vault(state: State<'_, AppState>, name: String) -> Result<(), String> {
    let mut lock = state.vault_manager.lock().await;
    let mgr = lock.as_mut().ok_or("Manager not initialized")?;
    mgr.delete_vault(&name).await
}

#[tauri::command]
async fn search_vault(
    state: State<'_, AppState>,
    vault_name: String,
    query: String,
    limit: Option<u64>,
) -> Result<Vec<SearchResult>, String> {
    let lock = state.vault_manager.lock().await;
    let mgr = lock.as_ref().ok_or("Manager not initialized")?;
    mgr.search(&vault_name, &query, limit.unwrap_or(10)).await
}

#[tauri::command]
async fn get_graph(state: State<'_, AppState>, vault_name: String) -> Result<GraphData, String> {
    let lock = state.vault_manager.lock().await;
    let mgr = lock.as_ref().ok_or("Manager not initialized")?;
    mgr.build_graph(&vault_name).await
}

#[tauri::command]
async fn get_file_tree(state: State<'_, AppState>, vault_name: String) -> Result<FileTreeNode, String> {
    let lock = state.vault_manager.lock().await;
    let mgr = lock.as_ref().ok_or("Manager not initialized")?;
    mgr.get_file_tree(&vault_name)
}

#[tauri::command]
async fn get_note_detail(
    state: State<'_, AppState>,
    vault_name: String,
    note_path: String,
) -> Result<NoteDetail, String> {
    let lock = state.vault_manager.lock().await;
    let mgr = lock.as_ref().ok_or("Manager not initialized")?;
    mgr.get_note_detail(&vault_name, &note_path).await
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .manage(AppState {
            vault_manager: Mutex::new(None),
        })
        .invoke_handler(tauri::generate_handler![
            init_manager,
            list_vaults,
            create_vault,
            delete_vault,
            search_vault,
            get_graph,
            get_file_tree,
            get_note_detail,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
