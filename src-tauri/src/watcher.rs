use notify::{Config, Event, EventKind, RecommendedWatcher, RecursiveMode, Watcher};
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter};

/// Events emitted to the frontend
#[derive(Clone, serde::Serialize)]
pub struct FileChangeEvent {
    pub vault_name: String,
    pub path: String,
    pub kind: String, // "create", "modify", "delete"
}

struct WatcherEntry {
    _watcher: RecommendedWatcher,
}

pub struct VaultWatcher {
    watchers: Arc<Mutex<HashMap<String, WatcherEntry>>>,
}

impl VaultWatcher {
    pub fn new() -> Self {
        Self {
            watchers: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    pub fn watch_vault(&self, vault_name: &str, source_path: &str, app: AppHandle) {
        let vault_name = vault_name.to_string();
        let source_path = PathBuf::from(source_path);

        let (tx, rx) = mpsc::channel::<Event>();

        let mut watcher = RecommendedWatcher::new(
            move |res: Result<Event, notify::Error>| {
                if let Ok(event) = res {
                    let _ = tx.send(event);
                }
            },
            Config::default().with_poll_interval(Duration::from_secs(2)),
        )
        .expect("Failed to create file watcher");

        watcher
            .watch(&source_path, RecursiveMode::Recursive)
            .expect("Failed to watch vault directory");

        let vn = vault_name.clone();

        // Debounce + dispatch thread
        thread::spawn(move || {
            // Track last event time per path to debounce
            let mut pending: HashMap<PathBuf, (String, Instant)> = HashMap::new();
            let debounce = Duration::from_secs(2);

            loop {
                // Drain all available events
                match rx.recv_timeout(Duration::from_millis(500)) {
                    Ok(event) => {
                        let kind = match event.kind {
                            EventKind::Create(_) => "create",
                            EventKind::Modify(_) => "modify",
                            EventKind::Remove(_) => "delete",
                            _ => continue,
                        };

                        for path in event.paths {
                            // Only care about .md files
                            if path.extension().map(|e| e != "md").unwrap_or(true) {
                                continue;
                            }
                            if path.to_string_lossy().contains(".trash") {
                                continue;
                            }
                            pending.insert(path, (kind.to_string(), Instant::now()));
                        }
                    }
                    Err(mpsc::RecvTimeoutError::Timeout) => {}
                    Err(mpsc::RecvTimeoutError::Disconnected) => break,
                }

                // Flush debounced events
                let now = Instant::now();
                let ready: Vec<(PathBuf, String)> = pending
                    .iter()
                    .filter(|(_, (_, ts))| now.duration_since(*ts) >= debounce)
                    .map(|(p, (k, _))| (p.clone(), k.clone()))
                    .collect();

                for (path, kind) in ready {
                    pending.remove(&path);
                    let event = FileChangeEvent {
                        vault_name: vn.clone(),
                        path: path.to_string_lossy().to_string(),
                        kind,
                    };
                    let _ = app.emit("vault-file-change", &event);
                }
            }
        });

        let mut watchers = self.watchers.lock().unwrap();
        watchers.insert(vault_name, WatcherEntry { _watcher: watcher });
    }

    pub fn unwatch_vault(&self, vault_name: &str) {
        let mut watchers = self.watchers.lock().unwrap();
        watchers.remove(vault_name);
    }
}
