use pulldown_cmark::{Event, Parser, Tag, TagEnd};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParsedNote {
    pub title: String,
    pub path: String,
    pub content: String,
    pub plain_text: String,
    pub links: Vec<String>,
    pub tags: Vec<String>,
    pub frontmatter: HashMap<String, String>,
    pub chunks: Vec<String>,
}

pub fn parse_markdown_file(path: &Path) -> Result<ParsedNote, String> {
    let raw = std::fs::read_to_string(path).map_err(|e| format!("Read error: {}", e))?;

    let title = path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("Untitled")
        .to_string();

    let (frontmatter, body) = extract_frontmatter(&raw);
    let links = extract_wikilinks(&body);
    let tags = extract_tags(&body, &frontmatter);
    let plain_text = markdown_to_plain(&body);
    let chunks = chunk_text(&plain_text, 512, 64);

    Ok(ParsedNote {
        title,
        path: path.to_string_lossy().to_string(),
        content: body.clone(),
        plain_text,
        links,
        tags,
        frontmatter,
        chunks,
    })
}

fn extract_frontmatter(raw: &str) -> (HashMap<String, String>, String) {
    let mut fm = HashMap::new();

    if !raw.starts_with("---") {
        return (fm, raw.to_string());
    }

    let parts: Vec<&str> = raw.splitn(3, "---").collect();
    if parts.len() < 3 {
        return (fm, raw.to_string());
    }

    let fm_block = parts[1].trim();
    for line in fm_block.lines() {
        if let Some((key, val)) = line.split_once(':') {
            fm.insert(key.trim().to_string(), val.trim().to_string());
        }
    }

    (fm, parts[2].to_string())
}

fn extract_wikilinks(text: &str) -> Vec<String> {
    let mut links = Vec::new();
    let mut chars = text.chars().peekable();

    while let Some(c) = chars.next() {
        if c == '[' {
            if chars.peek() == Some(&'[') {
                chars.next();
                let mut link = String::new();
                for inner in chars.by_ref() {
                    if inner == ']' {
                        break;
                    }
                    link.push(inner);
                }
                // Handle aliases: [[note|display]]
                let link_target = link.split('|').next().unwrap_or(&link).trim().to_string();
                if !link_target.is_empty() {
                    links.push(link_target);
                }
            }
        }
    }

    links
}

fn extract_tags(text: &str, fm: &HashMap<String, String>) -> Vec<String> {
    let mut tags = Vec::new();

    // Tags from frontmatter
    if let Some(fm_tags) = fm.get("tags") {
        let cleaned = fm_tags.trim_matches(|c| c == '[' || c == ']');
        for t in cleaned.split(',') {
            let t = t.trim().trim_matches('"').trim_matches('\'');
            if !t.is_empty() {
                tags.push(t.to_string());
            }
        }
    }

    // Inline #tags
    for word in text.split_whitespace() {
        if word.starts_with('#') && word.len() > 1 {
            let tag = word.trim_start_matches('#').trim_matches(|c: char| !c.is_alphanumeric() && c != '-' && c != '_');
            if !tag.is_empty() {
                tags.push(tag.to_string());
            }
        }
    }

    tags.sort();
    tags.dedup();
    tags
}

fn markdown_to_plain(md: &str) -> String {
    let parser = Parser::new(md);
    let mut plain = String::new();
    let mut in_code = false;

    for event in parser {
        match event {
            Event::Text(text) => {
                if !in_code {
                    plain.push_str(&text);
                    plain.push(' ');
                }
            }
            Event::SoftBreak | Event::HardBreak => plain.push('\n'),
            Event::Start(Tag::CodeBlock(_)) => in_code = true,
            Event::End(TagEnd::CodeBlock) => in_code = false,
            _ => {}
        }
    }

    plain.trim().to_string()
}

fn chunk_text(text: &str, chunk_size: usize, overlap: usize) -> Vec<String> {
    let words: Vec<&str> = text.split_whitespace().collect();
    if words.is_empty() {
        return vec![];
    }
    if words.len() <= chunk_size {
        return vec![words.join(" ")];
    }

    let mut chunks = Vec::new();
    let mut start = 0;

    while start < words.len() {
        let end = (start + chunk_size).min(words.len());
        chunks.push(words[start..end].join(" "));
        if end >= words.len() {
            break;
        }
        start += chunk_size - overlap;
    }

    chunks
}
