//! stegscan -- container-level steganalysis triage.
//!
//! Why this exists in Rust when the reference implementation is Python:
//! triage is the one part of the pipeline that is genuinely throughput-bound.
//! An analyst does not run a structural check on one file, they run it on a
//! disk image's worth of files, and the answer for most of them is "nothing
//! here". Python spends that time in interpreter overhead.
//!
//! What it deliberately does NOT do: anything statistical, anything needing
//! inflate, anything requiring judgement. Those live in Python where they are
//! easier to read, easier to change, and not on the hot path. This binary
//! answers exactly one question fast -- does every byte in this file have a
//! structural reason to exist? -- and hands anything interesting upstream.
//!
//! Its output is checked against the Python implementation file by file by
//! `scripts/difftest.py`. Two implementations that agree are evidence; one
//! implementation is an assertion.
//!
//! Usage:
//!   stegscan <path>...          scan files, emit JSON lines
//!   stegscan --bench <path>...  scan repeatedly and report throughput

use std::env;
use std::fs;
use std::io::{self, Write};
use std::path::Path;
use std::time::Instant;

mod crc32;
mod jpeg;
mod png;

#[derive(Debug, Default)]
pub struct Report {
    pub path: String,
    pub size: usize,
    pub kind: &'static str,
    pub structural_end: Option<usize>,
    pub trailing_bytes: usize,
    pub chunks: Vec<(String, usize, usize)>, // (type, offset, length)
    pub bad_crc: Vec<String>,
    pub unknown_chunks: Vec<String>,
    pub scan_bytes: usize,
    pub stuffed_ff: usize,
    pub restart_markers: usize,
    pub errors: Vec<String>,
}

impl Report {
    fn to_json(&self) -> String {
        let chunks: Vec<String> = self
            .chunks
            .iter()
            .map(|(t, o, l)| format!("[{},{},{}]", json_str(t), o, l))
            .collect();
        let bad: Vec<String> = self.bad_crc.iter().map(|s| json_str(s)).collect();
        let unk: Vec<String> = self.unknown_chunks.iter().map(|s| json_str(s)).collect();
        let errs: Vec<String> = self.errors.iter().map(|s| json_str(s)).collect();
        format!(
            concat!(
                "{{\"path\":{},\"size\":{},\"kind\":{},\"structural_end\":{},",
                "\"trailing_bytes\":{},\"chunks\":[{}],\"bad_crc\":[{}],",
                "\"unknown_chunks\":[{}],\"scan_bytes\":{},\"stuffed_ff\":{},",
                "\"restart_markers\":{},\"errors\":[{}]}}"
            ),
            json_str(&self.path),
            self.size,
            json_str(self.kind),
            match self.structural_end {
                Some(v) => v.to_string(),
                None => "null".to_string(),
            },
            self.trailing_bytes,
            chunks.join(","),
            bad.join(","),
            unk.join(","),
            self.scan_bytes,
            self.stuffed_ff,
            self.restart_markers,
            errs.join(",")
        )
    }
}

fn json_str(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

pub fn scan(path: &Path, data: &[u8]) -> Report {
    let mut report = Report {
        path: path.to_string_lossy().into_owned(),
        size: data.len(),
        kind: "unknown",
        ..Default::default()
    };

    if data.starts_with(png::MAGIC) {
        report.kind = "png";
        png::scan(data, &mut report);
    } else if data.len() >= 3 && data[0] == 0xFF && data[1] == 0xD8 && data[2] == 0xFF {
        report.kind = "jpeg";
        jpeg::scan(data, &mut report);
    } else {
        report.errors.push("unrecognised container".to_string());
    }

    if let Some(end) = report.structural_end {
        report.trailing_bytes = data.len().saturating_sub(end);
    }
    report
}

fn main() -> io::Result<()> {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.is_empty() {
        eprintln!("usage: stegscan [--bench] <path>...");
        std::process::exit(2);
    }

    let bench = args[0] == "--bench";
    let paths: Vec<&String> = if bench {
        args[1..].iter().collect()
    } else {
        args.iter().collect()
    };

    if bench {
        let blobs: Vec<(String, Vec<u8>)> = paths
            .iter()
            .filter_map(|p| fs::read(p).ok().map(|d| ((*p).clone(), d)))
            .collect();
        let total_bytes: usize = blobs.iter().map(|(_, d)| d.len()).sum();
        let rounds = 20;
        let start = Instant::now();
        let mut sink = 0usize;
        for _ in 0..rounds {
            for (p, d) in &blobs {
                sink += scan(Path::new(p), d).chunks.len();
            }
        }
        let elapsed = start.elapsed().as_secs_f64();
        let files = blobs.len() * rounds;
        println!(
            "{{\"files\":{},\"bytes\":{},\"seconds\":{:.6},\"files_per_sec\":{:.1},\"mb_per_sec\":{:.1},\"checksum\":{}}}",
            files,
            total_bytes * rounds,
            elapsed,
            files as f64 / elapsed,
            (total_bytes * rounds) as f64 / elapsed / 1_048_576.0,
            sink
        );
        return Ok(());
    }

    let stdout = io::stdout();
    let mut out = io::BufWriter::new(stdout.lock());
    for p in paths {
        match fs::read(p) {
            Ok(data) => {
                writeln!(out, "{}", scan(Path::new(p), &data).to_json())?;
            }
            Err(e) => {
                eprintln!("{}: {}", p, e);
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unknown_container_is_reported_not_panicked() {
        let r = scan(Path::new("x"), b"not an image");
        assert_eq!(r.kind, "unknown");
        assert_eq!(r.errors.len(), 1);
    }

    #[test]
    fn empty_input_is_safe() {
        let r = scan(Path::new("x"), b"");
        assert_eq!(r.size, 0);
    }

    #[test]
    fn json_escaping() {
        assert_eq!(json_str("a\"b"), "\"a\\\"b\"");
        assert_eq!(json_str("a\nb"), "\"a\\nb\"");
    }
}
