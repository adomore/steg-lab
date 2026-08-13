//! PNG chunk walk.
//!
//! The chunk-name property bits are encoded in the CASE of the four type
//! letters, and the ordering is easy to get wrong:
//!
//!   letter 1 lowercase -> ancillary
//!   letter 2 lowercase -> private        <- NOT letter 3
//!   letter 3 uppercase -> reserved bit
//!   letter 4 lowercase -> safe to copy
//!
//! The Python reference implementation had this wrong until gate G1 caught
//! it, so the same test lives on both sides of the port.

use crate::crc32::Crc32;
use crate::Report;

pub const MAGIC: &[u8] = b"\x89PNG\r\n\x1a\n";

pub const SPEC_CHUNKS: &[&str] = &[
    "IHDR", "PLTE", "IDAT", "IEND", "tRNS", "cHRM", "gAMA", "iCCP", "sBIT", "sRGB", "tEXt", "zTXt",
    "iTXt", "bKGD", "hIST", "pHYs", "sPLT", "tIME", "eXIf", "acTL", "fcTL", "fdAT", "cICP", "mDCv",
    "cLLi",
];

pub fn is_ancillary(t: &str) -> bool {
    t.as_bytes()[0].is_ascii_lowercase()
}

pub fn is_private(t: &str) -> bool {
    t.as_bytes()[1].is_ascii_lowercase()
}

pub fn reserved_bit_ok(t: &str) -> bool {
    t.as_bytes()[2].is_ascii_uppercase()
}

pub fn scan(data: &[u8], report: &mut Report) {
    let crc = Crc32::new();
    let mut pos = MAGIC.len();

    while pos + 8 <= data.len() {
        let length =
            u32::from_be_bytes([data[pos], data[pos + 1], data[pos + 2], data[pos + 3]]) as usize;
        let type_bytes = &data[pos + 4..pos + 8];
        let ctype = match std::str::from_utf8(type_bytes) {
            Ok(s) if s.chars().all(|c| c.is_ascii_alphabetic()) => s.to_string(),
            _ => {
                report
                    .errors
                    .push(format!("non-alphabetic chunk type at offset {}", pos));
                break;
            }
        };

        let data_end = pos + 8 + length;
        if data_end + 4 > data.len() {
            // Record the declaration before bailing out: "the file claims an
            // IDAT of N bytes that is not there" is itself a finding. It is
            // NOT a CRC failure, because there is no stored CRC to compare.
            report.chunks.push((ctype.clone(), pos, length));
            report.errors.push(format!(
                "chunk {} at {} declares {} bytes but the file ends early",
                ctype, pos, length
            ));
            break;
        }

        let stored = u32::from_be_bytes([
            data[data_end],
            data[data_end + 1],
            data[data_end + 2],
            data[data_end + 3],
        ]);
        let computed = crc.checksum(&data[pos + 4..data_end]);
        if stored != computed {
            report.bad_crc.push(ctype.clone());
        }
        if !SPEC_CHUNKS.contains(&ctype.as_str()) {
            report.unknown_chunks.push(ctype.clone());
        }
        report.chunks.push((ctype.clone(), pos, length));

        pos = data_end + 4;
        if ctype == "IEND" {
            report.structural_end = Some(pos);
            break;
        }
    }

    if report.structural_end.is_none() && report.errors.is_empty() {
        report.errors.push("no IEND chunk found".to_string());
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn property_bits_use_the_right_letters() {
        assert!(is_ancillary("stEG"));
        assert!(is_private("stEG"));
        assert!(reserved_bit_ok("stEG"));
        assert!(!is_ancillary("IHDR"));
        assert!(!is_private("IHDR"));
        // A chunk whose THIRD letter is lowercase is malformed, not private.
        assert!(!reserved_bit_ok("steG"));
    }

    #[test]
    fn truncated_file_yields_an_error() {
        let mut r = Report::default();
        let mut buf = MAGIC.to_vec();
        buf.extend_from_slice(&[0, 0, 0, 200]);
        buf.extend_from_slice(b"IHDR");
        scan(&buf, &mut r);
        assert!(!r.errors.is_empty());
    }
}
