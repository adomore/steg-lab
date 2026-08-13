//! JPEG marker walk with byte-stuffing-aware scan traversal.
//!
//! Searching for 0xFFD9 to find the end of a JPEG is wrong: compressed data
//! contains that pair by chance. Inside an entropy-coded scan a literal 0xFF
//! is stored as 0xFF 0x00, and only a non-zero, non-RST second byte ends the
//! scan. Walking that rule is the difference between finding the real EOI
//! and finding a coincidence.

use crate::Report;

const SOI: u8 = 0xD8;
const EOI: u8 = 0xD9;
const SOS: u8 = 0xDA;

fn is_standalone(m: u8) -> bool {
    m == 0x01 || m == SOI || m == EOI || (0xD0..=0xD7).contains(&m)
}

fn marker_name(m: u8) -> String {
    match m {
        0xC0 => "SOF0".into(),
        0xC1 => "SOF1".into(),
        0xC2 => "SOF2".into(),
        0xC4 => "DHT".into(),
        0xD8 => "SOI".into(),
        0xD9 => "EOI".into(),
        0xDA => "SOS".into(),
        0xDB => "DQT".into(),
        0xDD => "DRI".into(),
        0xFE => "COM".into(),
        m if (0xE0..=0xEF).contains(&m) => format!("APP{}", m - 0xE0),
        m if (0xD0..=0xD7).contains(&m) => format!("RST{}", m - 0xD0),
        m => format!("UNK{:02X}", m),
    }
}

/// Advance through an entropy-coded segment. Returns (end, stuffed, restarts).
fn scan_entropy(data: &[u8], mut pos: usize) -> (usize, usize, usize) {
    let mut stuffed = 0usize;
    let mut restarts = 0usize;
    while pos + 1 < data.len() {
        if data[pos] != 0xFF {
            pos += 1;
            continue;
        }
        let next = data[pos + 1];
        if next == 0x00 {
            stuffed += 1;
            pos += 2;
        } else if (0xD0..=0xD7).contains(&next) {
            restarts += 1;
            pos += 2;
        } else if next == 0xFF {
            pos += 1;
        } else {
            break;
        }
    }
    (pos, stuffed, restarts)
}

pub fn scan(data: &[u8], report: &mut Report) {
    report.chunks.push(("SOI".to_string(), 0, 0));
    let mut pos = 2usize;

    while pos + 1 < data.len() {
        if data[pos] != 0xFF {
            report.errors.push(format!(
                "expected a marker at offset {}, found 0x{:02x}",
                pos, data[pos]
            ));
            break;
        }
        let mut m = pos + 1;
        while m < data.len() && data[m] == 0xFF {
            m += 1;
        }
        if m >= data.len() {
            report.errors.push("file ends inside a marker".to_string());
            break;
        }
        let marker = data[m];
        let name = marker_name(marker);

        if marker == EOI {
            report.chunks.push(("EOI".to_string(), pos, 0));
            report.structural_end = Some(m + 1);
            break;
        }
        if is_standalone(marker) {
            report.chunks.push((name, pos, 0));
            pos = m + 1;
            continue;
        }
        if m + 3 > data.len() {
            report
                .errors
                .push(format!("truncated length field at offset {}", m));
            break;
        }
        let length = u16::from_be_bytes([data[m + 1], data[m + 2]]) as usize;
        if length < 2 {
            report.errors.push(format!(
                "segment {} at {} declares an impossible length {}",
                name, pos, length
            ));
            break;
        }
        report.chunks.push((name, pos, length));
        pos = m + 1 + length;

        if marker == SOS {
            let (end, stuffed, restarts) = scan_entropy(data, pos);
            report.scan_bytes += end - pos;
            report.stuffed_ff += stuffed;
            report.restart_markers += restarts;
            pos = end;
        }
    }

    if report.structural_end.is_none() && report.errors.is_empty() {
        report.errors.push("no EOI marker found".to_string());
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stuffed_ff_does_not_end_the_scan() {
        // FF 00 is a literal FF inside the scan; FF D9 ends it.
        let data = [0xFFu8, 0x00, 0x12, 0xFF, 0x00, 0xFF, 0xD9];
        let (end, stuffed, restarts) = scan_entropy(&data, 0);
        assert_eq!(end, 5);
        assert_eq!(stuffed, 2);
        assert_eq!(restarts, 0);
    }

    #[test]
    fn restart_markers_do_not_end_the_scan() {
        let data = [0xFFu8, 0xD0, 0xAB, 0xFF, 0xD7, 0xFF, 0xD9];
        let (end, _, restarts) = scan_entropy(&data, 0);
        assert_eq!(end, 5);
        assert_eq!(restarts, 2);
    }
}
