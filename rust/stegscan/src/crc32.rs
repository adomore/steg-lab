//! CRC-32 (IEEE 802.3), table-driven.
//!
//! PNG stores a CRC per chunk. Nothing in the decoding path verifies it,
//! which makes a stale CRC a reliable tell that a chunk's bytes were edited
//! after the file was written.

const POLY: u32 = 0xEDB8_8320;

pub struct Crc32 {
    table: [u32; 256],
}

impl Crc32 {
    pub const fn new() -> Self {
        let mut table = [0u32; 256];
        let mut i = 0usize;
        while i < 256 {
            let mut c = i as u32;
            let mut k = 0;
            while k < 8 {
                c = if c & 1 != 0 { POLY ^ (c >> 1) } else { c >> 1 };
                k += 1;
            }
            table[i] = c;
            i += 1;
        }
        Self { table }
    }

    pub fn checksum(&self, data: &[u8]) -> u32 {
        let mut c = 0xFFFF_FFFFu32;
        for &b in data {
            c = self.table[((c ^ b as u32) & 0xFF) as usize] ^ (c >> 8);
        }
        c ^ 0xFFFF_FFFF
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn known_vectors() {
        let crc = Crc32::new();
        assert_eq!(crc.checksum(b""), 0x0000_0000);
        assert_eq!(crc.checksum(b"123456789"), 0xCBF4_3926);
        assert_eq!(crc.checksum(b"IEND"), 0xAE42_6082);
    }
}
