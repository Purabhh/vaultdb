use qdrant_client::qdrant::{
    CreateCollectionBuilder, Distance, PointStruct, SearchPointsBuilder,
    VectorParamsBuilder, UpsertPointsBuilder, DeleteCollectionBuilder,
    DeletePointsBuilder, Filter, Condition,
    vectors_config::Config, VectorsConfig,
};
use qdrant_client::Qdrant;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use uuid::Uuid;
use walkdir::WalkDir;

use crate::embeddings::EmbeddingClient;
use crate::markdown::parse_markdown_file;

fn payload_str<'a>(payload: &'a HashMap<String, qdrant_client::qdrant::Value>, key: &str, default: &'a str) -> &'a str {
    payload.get(key).and_then(|v| v.as_str()).map(|s| s.as_str()).unwrap_or(default)
}

const EMBEDDING_DIM: u64 = 768; // nomic-embed-text dimension
const SEMANTIC_THRESHOLD: f32 = 0.55; // cosine similarity threshold for semantic edges

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VaultInfo {
    pub name: String,
    pub source_path: String,
    pub note_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    pub title: String,
    pub path: String,
    pub chunk: String,
    pub score: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphNode {
    pub id: String,
    pub title: String,
    pub path: String,
    pub tags: Vec<String>,
    pub link_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphEdge {
    pub source: String,
    pub target: String,
    pub edge_type: String, // "link" or "semantic"
    pub weight: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphData {
    pub nodes: Vec<GraphNode>,
    pub edges: Vec<GraphEdge>,
}

// File tree types
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileTreeNode {
    pub name: String,
    pub path: String,
    pub is_dir: bool,
    pub children: Vec<FileTreeNode>,
}

// Note detail with chunks and similar notes
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChunkDetail {
    pub index: usize,
    pub text: String,
    pub similar_notes: Vec<SimilarNote>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SimilarNote {
    pub title: String,
    pub chunk: String,
    pub score: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NoteDetail {
    pub title: String,
    pub path: String,
    pub raw_content: String,
    pub tags: Vec<String>,
    pub links: Vec<String>,
    pub chunks: Vec<ChunkDetail>,
}

pub struct VaultManager {
    qdrant: Qdrant,
    embedder: EmbeddingClient,
    config_path: PathBuf,
    vaults: HashMap<String, VaultInfo>,
}

#[derive(Serialize, Deserialize, Default)]
struct VaultConfig {
    vaults: HashMap<String, VaultInfo>,
}

impl VaultManager {
    pub async fn new() -> Result<Self, String> {
        let qdrant = Qdrant::from_url("http://localhost:6334")
            .build()
            .map_err(|e| format!("Failed to connect to Qdrant: {}", e))?;

        let config_dir = dirs_config_path();
        std::fs::create_dir_all(&config_dir).ok();
        let config_path = config_dir.join("vaults.json");

        let vaults = if config_path.exists() {
            let data = std::fs::read_to_string(&config_path).unwrap_or_default();
            serde_json::from_str::<VaultConfig>(&data)
                .unwrap_or_default()
                .vaults
        } else {
            HashMap::new()
        };

        Ok(Self {
            qdrant,
            embedder: EmbeddingClient::default(),
            config_path,
            vaults,
        })
    }

    fn save_config(&self) -> Result<(), String> {
        let config = VaultConfig {
            vaults: self.vaults.clone(),
        };
        let json = serde_json::to_string_pretty(&config).map_err(|e| e.to_string())?;
        std::fs::write(&self.config_path, json).map_err(|e| e.to_string())
    }

    pub fn list_vaults(&self) -> Vec<VaultInfo> {
        self.vaults.values().cloned().collect()
    }

    pub async fn create_vault(&mut self, name: &str, source_path: &str) -> Result<VaultInfo, String> {
        let collection_name = format!("vault_{}", name);

        // Create Qdrant collection
        self.qdrant
            .create_collection(
                CreateCollectionBuilder::new(&collection_name)
                    .vectors_config(VectorsConfig {
                        config: Some(Config::Params(
                            VectorParamsBuilder::new(EMBEDDING_DIM, Distance::Cosine).build(),
                        )),
                    }),
            )
            .await
            .map_err(|e| format!("Failed to create collection: {}", e))?;

        // Ingest markdown files
        let notes = self.ingest_directory(Path::new(source_path), &collection_name).await?;

        let info = VaultInfo {
            name: name.to_string(),
            source_path: source_path.to_string(),
            note_count: notes,
        };

        self.vaults.insert(name.to_string(), info.clone());
        self.save_config()?;

        Ok(info)
    }

    pub async fn delete_vault(&mut self, name: &str) -> Result<(), String> {
        let collection_name = format!("vault_{}", name);
        self.qdrant
            .delete_collection(DeleteCollectionBuilder::new(&collection_name))
            .await
            .map_err(|e| format!("Failed to delete collection: {}", e))?;

        self.vaults.remove(name);
        self.save_config()?;
        Ok(())
    }

    async fn ingest_directory(&self, dir: &Path, collection: &str) -> Result<usize, String> {
        let mut count = 0;
        let mut all_points = Vec::new();

        let md_files: Vec<_> = WalkDir::new(dir)
            .into_iter()
            .filter_map(|e| e.ok())
            .filter(|e| {
                e.path().extension().map(|ext| ext == "md").unwrap_or(false)
                    && !e.path().to_string_lossy().contains(".trash")
            })
            .collect();

        for entry in &md_files {
            let note = match parse_markdown_file(entry.path()) {
                Ok(n) => n,
                Err(_) => continue,
            };

            if note.chunks.is_empty() {
                continue;
            }

            // Embed all chunks for this note
            let embeddings = match self.embedder.embed(note.chunks.clone()).await {
                Ok(e) => e,
                Err(_) => continue,
            };

            let links_json = serde_json::to_string(&note.links).unwrap_or_default();
            let tags_json = serde_json::to_string(&note.tags).unwrap_or_default();

            for (i, (chunk, embedding)) in note.chunks.iter().zip(embeddings.iter()).enumerate() {
                let point_id = Uuid::new_v4().to_string();
                let payload: HashMap<String, qdrant_client::qdrant::Value> = HashMap::from([
                    ("title".to_string(), note.title.clone().into()),
                    ("path".to_string(), note.path.clone().into()),
                    ("chunk".to_string(), chunk.clone().into()),
                    ("chunk_index".to_string(), (i as i64).into()),
                    ("links".to_string(), links_json.clone().into()),
                    ("tags".to_string(), tags_json.clone().into()),
                ]);

                all_points.push(PointStruct::new(point_id, embedding.clone(), payload));
            }

            count += 1;
        }

        // Batch upsert
        if !all_points.is_empty() {
            // Upsert in batches of 100
            for batch in all_points.chunks(100) {
                self.qdrant
                    .upsert_points(UpsertPointsBuilder::new(collection, batch.to_vec()))
                    .await
                    .map_err(|e| format!("Upsert failed: {}", e))?;
            }
        }

        Ok(count)
    }

    pub async fn search(&self, vault_name: &str, query: &str, limit: u64) -> Result<Vec<SearchResult>, String> {
        let collection = format!("vault_{}", vault_name);
        let query_vec = self.embedder.embed_one(query).await?;

        let results = self
            .qdrant
            .search_points(
                SearchPointsBuilder::new(&collection, query_vec, limit).with_payload(true),
            )
            .await
            .map_err(|e| format!("Search failed: {}", e))?;

        let search_results = results
            .result
            .into_iter()
            .map(|point| {
                let payload = point.payload;
                SearchResult {
                    title: payload_str(&payload, "title", "").to_string(),
                    path: payload_str(&payload, "path", "").to_string(),
                    chunk: payload_str(&payload, "chunk", "").to_string(),
                    score: point.score,
                }
            })
            .collect();

        Ok(search_results)
    }

    pub async fn build_graph(&self, vault_name: &str) -> Result<GraphData, String> {
        let collection = format!("vault_{}", vault_name);

        // Scroll all points with vectors for semantic similarity
        let scroll_result = self
            .qdrant
            .scroll(
                qdrant_client::qdrant::ScrollPointsBuilder::new(&collection)
                    .with_payload(true)
                    .with_vectors(true)
                    .limit(10000),
            )
            .await
            .map_err(|e| format!("Scroll failed: {}", e))?;

        let mut nodes_map: HashMap<String, GraphNode> = HashMap::new();
        let mut edges: Vec<GraphEdge> = Vec::new();

        // Collect per-note average vectors for semantic edges
        let mut note_vectors: HashMap<String, Vec<Vec<f32>>> = HashMap::new();

        // Collect raw link data per note — resolve after all nodes are built
        let mut pending_links: Vec<(String, Vec<String>)> = Vec::new();

        // Build nodes from unique titles
        for point in &scroll_result.result {
            let payload = &point.payload;
            let title = payload_str(payload, "title", "").to_string();
            let path = payload_str(payload, "path", "").to_string();
            let tags_str = payload_str(payload, "tags", "[]");
            let tags: Vec<String> = serde_json::from_str(tags_str).unwrap_or_default();
            let links_str = payload_str(payload, "links", "[]");
            let links: Vec<String> = serde_json::from_str(links_str).unwrap_or_default();

            // Extract vector for semantic edges
            if let Some(vectors) = &point.vectors {
                if let Some(qdrant_client::qdrant::vectors_output::VectorsOptions::Vector(v)) = &vectors.vectors_options {
                    note_vectors.entry(title.clone()).or_default().push(v.data.clone());
                }
            }

            let node = nodes_map.entry(title.clone()).or_insert_with(|| GraphNode {
                id: title.clone(),
                title: title.clone(),
                path,
                tags,
                link_count: 0,
            });
            node.link_count = links.len();

            if !links.is_empty() {
                pending_links.push((title.clone(), links));
            }
        }

        // Resolve wikilinks like Obsidian: match by filename, ignoring path prefixes,
        // heading anchors, and case. Create ghost nodes for unresolved links.
        // Generate backlinks (bidirectional edges).
        let all_titles: Vec<String> = nodes_map.keys().cloned().collect();
        let mut edge_set: std::collections::HashSet<(String, String)> = std::collections::HashSet::new();

        for (source_title, links) in &pending_links {
            for link in links {
                // Strip heading anchor: "note#heading" → "note"
                let link_no_anchor = link.split('#').next().unwrap_or(link);
                // Strip path prefix: "2d-tutor/overview" → "overview"
                let link_name = link_no_anchor.rsplit('/').next().unwrap_or(link_no_anchor);

                if link_name.is_empty() { continue; }

                // Try exact match first, then case-insensitive
                let resolved = if nodes_map.contains_key(link_name) {
                    Some(link_name.to_string())
                } else if nodes_map.contains_key(link_no_anchor) {
                    Some(link_no_anchor.to_string())
                } else {
                    let lower = link_name.to_lowercase();
                    all_titles.iter().find(|t| t.to_lowercase() == lower).cloned()
                };

                let target = match resolved {
                    Some(t) => t,
                    None => {
                        // Create ghost node for unresolved link
                        let ghost_title = link_name.to_string();
                        nodes_map.entry(ghost_title.clone()).or_insert_with(|| GraphNode {
                            id: ghost_title.clone(),
                            title: ghost_title.clone(),
                            path: String::new(), // ghost — no file on disk
                            tags: vec![],
                            link_count: 0,
                        });
                        ghost_title
                    }
                };

                if target != *source_title {
                    // Forward edge: source → target
                    if edge_set.insert((source_title.clone(), target.clone())) {
                        edges.push(GraphEdge {
                            source: source_title.clone(),
                            target: target.clone(),
                            edge_type: "link".to_string(),
                            weight: 1.0,
                        });
                    }
                    // Backlink edge: target → source
                    if edge_set.insert((target.clone(), source_title.clone())) {
                        edges.push(GraphEdge {
                            source: target,
                            target: source_title.clone(),
                            edge_type: "backlink".to_string(),
                            weight: 0.8,
                        });
                    }
                }
            }
        }

        // Tag-based connections: notes sharing the same tag get a "tag" edge
        let mut tag_to_notes: HashMap<String, Vec<String>> = HashMap::new();
        for (title, node) in &nodes_map {
            for tag in &node.tags {
                tag_to_notes.entry(tag.clone()).or_default().push(title.clone());
            }
        }
        for (_tag, notes) in &tag_to_notes {
            if notes.len() < 2 || notes.len() > 20 { continue; } // skip very common tags
            for i in 0..notes.len() {
                for j in (i + 1)..notes.len() {
                    let a = &notes[i];
                    let b = &notes[j];
                    if !edge_set.contains(&(a.clone(), b.clone())) {
                        edge_set.insert((a.clone(), b.clone()));
                        edges.push(GraphEdge {
                            source: a.clone(),
                            target: b.clone(),
                            edge_type: "tag".to_string(),
                            weight: 0.5,
                        });
                    }
                }
            }
        }

        // Compute average vectors per note, then add semantic edges
        let mut avg_vectors: HashMap<String, Vec<f32>> = HashMap::new();
        for (title, vecs) in &note_vectors {
            if vecs.is_empty() { continue; }
            let dim = vecs[0].len();
            let mut avg = vec![0.0f32; dim];
            for v in vecs {
                for (i, val) in v.iter().enumerate() {
                    avg[i] += val;
                }
            }
            let n = vecs.len() as f32;
            for val in avg.iter_mut() {
                *val /= n;
            }
            avg_vectors.insert(title.clone(), avg);
        }

        // Compare all note pairs for semantic similarity
        let titles: Vec<&String> = avg_vectors.keys().collect();
        for i in 0..titles.len() {
            for j in (i + 1)..titles.len() {
                let sim = cosine_similarity(
                    &avg_vectors[titles[i]],
                    &avg_vectors[titles[j]],
                );
                if sim > SEMANTIC_THRESHOLD {
                    edges.push(GraphEdge {
                        source: titles[i].clone(),
                        target: titles[j].clone(),
                        edge_type: "semantic".to_string(),
                        weight: sim,
                    });
                }
            }
        }

        let nodes: Vec<GraphNode> = nodes_map.into_values().collect();

        Ok(GraphData { nodes, edges })
    }

    pub fn get_file_tree(&self, vault_name: &str) -> Result<FileTreeNode, String> {
        let vault = self.vaults.get(vault_name)
            .ok_or_else(|| format!("Vault '{}' not found", vault_name))?;
        let root_path = Path::new(&vault.source_path);
        build_file_tree(root_path, root_path)
    }

    /// Validate that a path is inside the vault's source directory (prevents path traversal)
    fn validate_path(&self, vault_name: &str, note_path: &str) -> Result<PathBuf, String> {
        let vault = self.vaults.get(vault_name)
            .ok_or_else(|| format!("Vault '{}' not found", vault_name))?;
        let source = std::fs::canonicalize(&vault.source_path)
            .map_err(|e| format!("Cannot resolve vault path: {}", e))?;
        let target = std::fs::canonicalize(note_path)
            .or_else(|_| {
                // File might not exist yet (create_note), canonicalize parent instead
                let p = Path::new(note_path);
                if let Some(parent) = p.parent() {
                    std::fs::canonicalize(parent).map(|cp| cp.join(p.file_name().unwrap_or_default()))
                } else {
                    Err(std::io::Error::new(std::io::ErrorKind::NotFound, "invalid path"))
                }
            })
            .map_err(|e| format!("Cannot resolve note path: {}", e))?;
        if !target.starts_with(&source) {
            return Err("Path traversal denied: note is outside the vault".to_string());
        }
        Ok(target)
    }

    pub async fn save_note(&self, vault_name: &str, note_path: &str, content: &str) -> Result<(), String> {
        let validated = self.validate_path(vault_name, note_path)?;
        std::fs::write(&validated, content)
            .map_err(|e| format!("Failed to write file: {}", e))
    }

    pub async fn reembed_note(&self, vault_name: &str, note_path: &str) -> Result<NoteDetail, String> {
        let validated = self.validate_path(vault_name, note_path)?;
        let collection = format!("vault_{}", vault_name);

        // Delete old Qdrant points for this note
        let path_filter = Filter::must(vec![
            Condition::matches("path", note_path.to_string()),
        ]);
        self.qdrant
            .delete_points(
                DeletePointsBuilder::new(&collection)
                    .points(path_filter),
            )
            .await
            .map_err(|e| format!("Failed to delete old points: {}", e))?;

        // Re-parse the file
        let note = parse_markdown_file(&validated)
            .map_err(|e| format!("Failed to parse: {}", e))?;

        // Re-embed and upsert new chunks
        if !note.chunks.is_empty() {
            let embeddings = self.embedder.embed(note.chunks.clone()).await
                .map_err(|e| format!("Re-embed failed: {}. Is Ollama running?", e))?;

            let links_json = serde_json::to_string(&note.links).unwrap_or_default();
            let tags_json = serde_json::to_string(&note.tags).unwrap_or_default();

            let points: Vec<PointStruct> = note.chunks.iter().zip(embeddings.iter()).enumerate()
                .map(|(i, (chunk, embedding))| {
                    let payload: HashMap<String, qdrant_client::qdrant::Value> = HashMap::from([
                        ("title".to_string(), note.title.clone().into()),
                        ("path".to_string(), note.path.clone().into()),
                        ("chunk".to_string(), chunk.clone().into()),
                        ("chunk_index".to_string(), (i as i64).into()),
                        ("links".to_string(), links_json.clone().into()),
                        ("tags".to_string(), tags_json.clone().into()),
                    ]);
                    PointStruct::new(Uuid::new_v4().to_string(), embedding.clone(), payload)
                })
                .collect();

            for batch in points.chunks(100) {
                self.qdrant
                    .upsert_points(UpsertPointsBuilder::new(&collection, batch.to_vec()))
                    .await
                    .map_err(|e| format!("Upsert failed: {}", e))?;
            }
        }

        // Return updated NoteDetail
        self.get_note_detail(vault_name, note_path).await
    }

    pub async fn create_note(&mut self, vault_name: &str, parent_dir: &str, file_name: &str) -> Result<String, String> {
        let vault = self.vaults.get(vault_name)
            .ok_or_else(|| format!("Vault '{}' not found", vault_name))?;

        // Validate parent_dir is inside vault
        let source = std::fs::canonicalize(&vault.source_path)
            .map_err(|e| format!("Cannot resolve vault path: {}", e))?;
        let parent = std::fs::canonicalize(parent_dir)
            .map_err(|e| format!("Cannot resolve parent dir: {}", e))?;
        if !parent.starts_with(&source) {
            return Err("Path traversal denied: directory is outside the vault".to_string());
        }

        let sanitized = file_name.trim().replace(['/', '\\'], "");
        let name = if sanitized.ends_with(".md") {
            sanitized
        } else {
            format!("{}.md", sanitized)
        };

        let full_path = parent.join(&name);
        if full_path.exists() {
            return Err(format!("File already exists: {}", full_path.display()));
        }

        let title = name.trim_end_matches(".md");
        let content = format!("# {}\n", title);
        std::fs::write(&full_path, &content)
            .map_err(|e| format!("Failed to create file: {}", e))?;

        // Update note count
        if let Some(info) = self.vaults.get_mut(vault_name) {
            info.note_count += 1;
            self.save_config()?;
        }

        Ok(full_path.to_string_lossy().to_string())
    }

    pub async fn delete_note(&mut self, vault_name: &str, note_path: &str) -> Result<(), String> {
        let validated = self.validate_path(vault_name, note_path)?;
        let collection = format!("vault_{}", vault_name);

        // Delete file from disk
        std::fs::remove_file(&validated)
            .map_err(|e| format!("Failed to delete file: {}", e))?;

        // Delete all Qdrant points for this note
        let path_filter = Filter::must(vec![
            Condition::matches("path", note_path.to_string()),
        ]);
        self.qdrant
            .delete_points(
                DeletePointsBuilder::new(&collection)
                    .points(path_filter),
            )
            .await
            .map_err(|e| format!("Failed to delete points: {}", e))?;

        // Update note count
        if let Some(info) = self.vaults.get_mut(vault_name) {
            if info.note_count > 0 {
                info.note_count -= 1;
            }
            self.save_config()?;
        }

        Ok(())
    }

    pub fn create_folder(&self, vault_name: &str, parent_dir: &str, folder_name: &str) -> Result<String, String> {
        let vault = self.vaults.get(vault_name)
            .ok_or_else(|| format!("Vault '{}' not found", vault_name))?;
        let source = std::fs::canonicalize(&vault.source_path)
            .map_err(|e| format!("Cannot resolve vault path: {}", e))?;
        let parent = std::fs::canonicalize(parent_dir)
            .map_err(|e| format!("Cannot resolve parent dir: {}", e))?;
        if !parent.starts_with(&source) {
            return Err("Path traversal denied: directory is outside the vault".to_string());
        }

        let sanitized = folder_name.trim().replace(['/', '\\'], "");
        if sanitized.is_empty() {
            return Err("Folder name cannot be empty".to_string());
        }

        let full_path = parent.join(&sanitized);
        if full_path.exists() {
            return Err(format!("Folder already exists: {}", full_path.display()));
        }

        std::fs::create_dir(&full_path)
            .map_err(|e| format!("Failed to create folder: {}", e))?;

        Ok(full_path.to_string_lossy().to_string())
    }

    pub fn delete_folder(&self, vault_name: &str, folder_path: &str) -> Result<(), String> {
        let vault = self.vaults.get(vault_name)
            .ok_or_else(|| format!("Vault '{}' not found", vault_name))?;
        let source = std::fs::canonicalize(&vault.source_path)
            .map_err(|e| format!("Cannot resolve vault path: {}", e))?;
        let target = std::fs::canonicalize(folder_path)
            .map_err(|e| format!("Cannot resolve folder path: {}", e))?;
        if !target.starts_with(&source) || target == source {
            return Err("Cannot delete vault root or paths outside the vault".to_string());
        }

        // Check if folder is empty (only allow deleting empty folders, or force with contents)
        let entries: Vec<_> = std::fs::read_dir(&target)
            .map_err(|e| format!("Cannot read folder: {}", e))?
            .collect();
        if entries.is_empty() {
            std::fs::remove_dir(&target)
                .map_err(|e| format!("Failed to delete folder: {}", e))?;
        } else {
            std::fs::remove_dir_all(&target)
                .map_err(|e| format!("Failed to delete folder: {}", e))?;
        }

        Ok(())
    }

    /// Create a brand new empty vault directory and register it
    pub async fn create_new_vault(&mut self, name: &str, parent_dir: &str) -> Result<VaultInfo, String> {
        let sanitized = name.trim().replace(['/', '\\'], "");
        if sanitized.is_empty() {
            return Err("Vault name cannot be empty".to_string());
        }

        let vault_dir = Path::new(parent_dir).join(&sanitized);
        if vault_dir.exists() {
            return Err(format!("Directory already exists: {}", vault_dir.display()));
        }

        std::fs::create_dir_all(&vault_dir)
            .map_err(|e| format!("Failed to create vault directory: {}", e))?;

        let collection_name = format!("vault_{}", sanitized);
        self.qdrant
            .create_collection(
                CreateCollectionBuilder::new(&collection_name)
                    .vectors_config(VectorsConfig {
                        config: Some(Config::Params(
                            VectorParamsBuilder::new(EMBEDDING_DIM, Distance::Cosine).build(),
                        )),
                    }),
            )
            .await
            .map_err(|e| format!("Failed to create collection: {}", e))?;

        let info = VaultInfo {
            name: sanitized.clone(),
            source_path: vault_dir.to_string_lossy().to_string(),
            note_count: 0,
        };

        self.vaults.insert(sanitized, info.clone());
        self.save_config()?;

        Ok(info)
    }

    pub fn rename_item(&self, vault_name: &str, old_path: &str, new_name: &str) -> Result<String, String> {
        let vault = self.vaults.get(vault_name)
            .ok_or_else(|| format!("Vault '{}' not found", vault_name))?;
        let source = std::fs::canonicalize(&vault.source_path)
            .map_err(|e| format!("Cannot resolve vault path: {}", e))?;
        let old = std::fs::canonicalize(old_path)
            .map_err(|e| format!("Cannot resolve path: {}", e))?;
        if !old.starts_with(&source) {
            return Err("Path traversal denied".to_string());
        }

        let sanitized = new_name.trim().replace(['/', '\\'], "");
        if sanitized.is_empty() {
            return Err("Name cannot be empty".to_string());
        }

        let new_path = old.parent()
            .ok_or("Cannot get parent directory")?
            .join(&sanitized);
        if new_path.exists() {
            return Err(format!("'{}' already exists", sanitized));
        }

        std::fs::rename(&old, &new_path)
            .map_err(|e| format!("Failed to rename: {}", e))?;

        Ok(new_path.to_string_lossy().to_string())
    }

    pub async fn get_note_detail(&self, vault_name: &str, note_path: &str) -> Result<NoteDetail, String> {
        let collection = format!("vault_{}", vault_name);

        // Read the raw file
        let raw_content = std::fs::read_to_string(note_path)
            .map_err(|e| format!("Failed to read file: {}", e))?;

        let note = parse_markdown_file(Path::new(note_path))
            .map_err(|e| format!("Failed to parse: {}", e))?;

        // Get this note's chunks from Qdrant with vectors
        let scroll_result = self
            .qdrant
            .scroll(
                qdrant_client::qdrant::ScrollPointsBuilder::new(&collection)
                    .with_payload(true)
                    .with_vectors(true)
                    .limit(10000),
            )
            .await
            .map_err(|e| format!("Scroll failed: {}", e))?;

        // Find chunks belonging to this note and search for similar ones
        let mut chunks = Vec::new();
        for point in &scroll_result.result {
            let payload = &point.payload;
            let p = payload_str(payload, "path", "");
            if p != note_path { continue; }

            let chunk_text = payload_str(payload, "chunk", "").to_string();
            let chunk_idx_val = payload.get("chunk_index")
                .and_then(|v| v.as_integer())
                .unwrap_or(0) as usize;

            // Get the vector for this chunk to search for similar
            let mut similar_notes = Vec::new();
            if let Some(vectors) = &point.vectors {
                if let Some(qdrant_client::qdrant::vectors_output::VectorsOptions::Vector(v)) = &vectors.vectors_options {
                    // Search for similar chunks (excluding same note)
                    if let Ok(results) = self.qdrant.search_points(
                        SearchPointsBuilder::new(&collection, v.data.clone(), 6)
                            .with_payload(true),
                    ).await {
                        for r in results.result {
                            let r_title = payload_str(&r.payload, "title", "").to_string();
                            if r_title == note.title { continue; }
                            similar_notes.push(SimilarNote {
                                title: r_title,
                                chunk: payload_str(&r.payload, "chunk", "").to_string(),
                                score: r.score,
                            });
                        }
                    }
                }
            }

            chunks.push(ChunkDetail {
                index: chunk_idx_val,
                text: chunk_text,
                similar_notes,
            });
        }

        chunks.sort_by_key(|c| c.index);

        Ok(NoteDetail {
            title: note.title,
            path: note_path.to_string(),
            raw_content,
            tags: note.tags,
            links: note.links,
            chunks,
        })
    }
}

fn build_file_tree(path: &Path, root: &Path) -> Result<FileTreeNode, String> {
    let name = path.file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("root")
        .to_string();

    if path.is_dir() {
        let mut children: Vec<FileTreeNode> = Vec::new();
        let entries = std::fs::read_dir(path).map_err(|e| e.to_string())?;

        for entry in entries {
            let entry = entry.map_err(|e| e.to_string())?;
            let entry_path = entry.path();
            let entry_name = entry_path.file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("");

            // Skip hidden dirs and .trash
            if entry_name.starts_with('.') { continue; }

            if entry_path.is_dir() {
                if let Ok(child) = build_file_tree(&entry_path, root) {
                    children.push(child);
                }
            } else if entry_path.extension().map(|e| e == "md").unwrap_or(false) {
                children.push(FileTreeNode {
                    name: entry_name.to_string(),
                    path: entry_path.to_string_lossy().to_string(),
                    is_dir: false,
                    children: vec![],
                });
            }
        }

        // Sort: dirs first, then files, alphabetically
        children.sort_by(|a, b| {
            match (a.is_dir, b.is_dir) {
                (true, false) => std::cmp::Ordering::Less,
                (false, true) => std::cmp::Ordering::Greater,
                _ => a.name.to_lowercase().cmp(&b.name.to_lowercase()),
            }
        });

        Ok(FileTreeNode { name, path: path.to_string_lossy().to_string(), is_dir: true, children })
    } else {
        Ok(FileTreeNode { name, path: path.to_string_lossy().to_string(), is_dir: false, children: vec![] })
    }
}

fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
    let mut dot = 0.0f32;
    let mut norm_a = 0.0f32;
    let mut norm_b = 0.0f32;
    for i in 0..a.len().min(b.len()) {
        dot += a[i] * b[i];
        norm_a += a[i] * a[i];
        norm_b += b[i] * b[i];
    }
    let denom = norm_a.sqrt() * norm_b.sqrt();
    if denom == 0.0 { 0.0 } else { dot / denom }
}

fn dirs_config_path() -> PathBuf {
    dirs::config_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("vaultdb")
}
