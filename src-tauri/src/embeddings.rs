use reqwest::Client;
use serde::{Deserialize, Serialize};

#[derive(Serialize)]
struct OllamaEmbedRequest {
    model: String,
    input: Vec<String>,
}

#[derive(Deserialize)]
struct OllamaEmbedResponse {
    embeddings: Vec<Vec<f32>>,
}

pub struct EmbeddingClient {
    client: Client,
    base_url: String,
    model: String,
}

impl EmbeddingClient {
    pub fn new(base_url: &str, model: &str) -> Self {
        Self {
            client: Client::new(),
            base_url: base_url.to_string(),
            model: model.to_string(),
        }
    }

    pub fn default() -> Self {
        Self::new("http://localhost:11434", "nomic-embed-text")
    }

    pub async fn embed(&self, texts: Vec<String>) -> Result<Vec<Vec<f32>>, String> {
        let req = OllamaEmbedRequest {
            model: self.model.clone(),
            input: texts,
        };

        let resp = self
            .client
            .post(format!("{}/api/embed", self.base_url))
            .json(&req)
            .send()
            .await
            .map_err(|e| format!("Ollama request failed: {}. Is Ollama running?", e))?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            return Err(format!("Ollama returned {}: {}", status, body));
        }

        let data: OllamaEmbedResponse = resp
            .json()
            .await
            .map_err(|e| format!("Failed to parse Ollama response: {}", e))?;

        Ok(data.embeddings)
    }

    pub async fn embed_one(&self, text: &str) -> Result<Vec<f32>, String> {
        let mut results = self.embed(vec![text.to_string()]).await?;
        results
            .pop()
            .ok_or_else(|| "No embedding returned".to_string())
    }
}
